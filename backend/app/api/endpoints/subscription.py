"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).

- GET /sub/{subscription_token}/open/{client} — 302 на ту же страницу на origin SPA (если API и сайт разъехались).
- GET /sub/{subscription_token}/open/{client}/data — JSON для попытки диплинка (Vue /sub/…/open/…); скачивание — /apps/{client}.
- Неизвестный client → 302 в кабинет.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import URL as StarletteURL
from starlette.requests import Request

from app.api.deps import ReadonlySessionDep
from app.core.config import settings
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.domain.subscription_public_base import (
    prefer_https_subscription_public_base,
    subscription_public_base_from_setting,
)
from app.domain.subscription_open_apps import (
    AppStoreLinks,
    get_subscription_open_app,
    list_subscription_open_app_codes,
)
from app.models.user import User
from app.schemas.subscription_open_page import SubscriptionOpenPageData
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)

router = APIRouter(tags=["public"])

# Имя path-параметра не «token»: иначе Swagger UI подставляет example=token и URL выглядит как /sub/token/... .
_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE = "R7k4mN9pQ2sT5vX8yZ1aB3cD6eF0gH2j"
_SUBSCRIPTION_TOKEN_PATH = Path(
    ...,
    description="Токен подписки (users.token), сегмент пути /sub/…/…",
    examples=[_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE],
)

_OPEN_APPS_DOC = ", ".join(list_subscription_open_app_codes())

_STORE_PLATFORM_KEYS = frozenset({"windows", "android", "ios", "macos", "linux"})


def _normalize_store_platform(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    return v if v in _STORE_PLATFORM_KEYS else None


def _cabinet_redirect_url(*, extra_query: dict[str, str] | None = None) -> str:
    raw = (settings.public_cabinet_url or "").strip().rstrip("/")
    if not raw:
        path = "/cabinet"
    elif raw.startswith(("http://", "https://")):
        path = raw
    else:
        path = raw if raw.startswith("/") else f"/{raw}"
    if extra_query:
        q = urlencode(extra_query)
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}{q}"
    return path


def _infer_public_origin_from_request(request: Request) -> str:
    """Публичный origin, когда SUBSCRIPTION_PUBLIC_BASE_URL не задан.

    Uvicorn по умолчанию доверяет только 127.0.0.1 для подстановки X-Forwarded-* в scope;
    за nginx в Docker подключение часто идёт не с loopback — scheme остаётся http, хотя у
    клиента HTTPS. Явно читаем заголовки, которые прокси уже выставил к бэкенду.
    """

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto not in ("http", "https"):
        forwarded_proto = request.url.scheme

    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    host = forwarded_host or (request.headers.get("host") or "").split(",")[0].strip()
    if host:
        netloc = host
    else:
        netloc = request.url.netloc

    return f"{forwarded_proto}://{netloc}".rstrip("/")


def _resolve_public_base(request: Request, configured_base: str) -> str:
    configured = subscription_public_base_from_setting(configured_base)
    if configured:
        return configured
    return prefer_https_subscription_public_base(_infer_public_origin_from_request(request))


def _resolve_spa_base(request: Request) -> str:
    raw = (settings.subscription_open_spa_base_url or "").strip().rstrip("/")
    if raw:
        return raw
    return _resolve_public_base(request, settings.subscription_public_base_url)


def _open_subscription_spa_url(
    request: Request,
    subscription_token: str,
    client: str,
    *,
    platform: str | None,
) -> str:
    base = _resolve_spa_base(request)
    t = quote(subscription_token, safe="")
    c = quote(client, safe="")
    path = f"{base}/sub/{t}/open/{c}"
    q: dict[str, str] = {}
    norm = _normalize_store_platform(platform)
    if norm:
        q["platform"] = norm
    if q:
        return f"{path}?{urlencode(q)}"
    return path


def _open_redirect_would_loop(request: Request, redirect_url: str) -> bool:
    """Редирект на тот же URL (часто: запрос на голый uvicorn вместо Vite/nginx)."""
    try:
        target = StarletteURL(redirect_url)
        cur = request.url
    except Exception:
        return False
    return (
        target.scheme == cur.scheme
        and target.netloc == cur.netloc
        and target.path == cur.path
        and str(target.query) == str(cur.query)
    )


async def _subscription_payload_for_token(
    subscription_token: str, session: ReadonlySessionDep
) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    if not user_has_active_subscription(user):
        return SubscriptionPayload(
            valid_until=user.subscription_until,
            subscription_active=False,
            servers=[],
            vless_uris=[],
            subscription_base64="",
        )

    rows = await run_in_threadpool(subscription_servers_after_prometheus_sync)
    return build_subscription_payload(user, rows)


def _build_open_page_data(
    request: Request,
    user: User | None,
    app,
    *,
    store_platform: str | None,
) -> SubscriptionOpenPageData:
    forced = _normalize_store_platform(store_platform)
    title = f"Подключение — {app.display_name}"
    headline = title
    open_label = f"Открыть в {app.display_name}"
    lead = (
        "Один раз пробуем открыть приложение, если оно уже установлено. "
        "Если приложение не установлено - нажмите кнопку Скачать или перейдите на сайт приложения"
    )
    hint = (
        "Если приложение не открылось, но установлено - нажмите «Открыть». "
    )

    if user is None:
        return SubscriptionOpenPageData(
            state="invalid_token",
            title="Ссылка недействительна",
            headline="Ссылка недействительна",
            message="Проверьте ссылку или получите новую в боте / личном кабинете.",
            deeplink=None,
            open_button_label="",
            lead=None,
            hint=None,
            store_links=None,
            forced_platform=forced,
        )

    if not user_has_active_subscription(user):
        return SubscriptionOpenPageData(
            state="inactive",
            title="Подписка не активна",
            headline="Подписка не активна",
            message="Продлите подписку и попробуйте снова.",
            deeplink=None,
            open_button_label="",
            lead=None,
            hint=None,
            store_links=None,
            forced_platform=forced,
        )

    base = _resolve_public_base(request, settings.subscription_public_base_url)
    subscription_url = f"{base}/sub/{user.token}"
    deeplink = app.build_deeplink(subscription_url)
    sl: AppStoreLinks = app.store_links
    store_json = sl.to_public_json_dict() if sl.any() else None

    return SubscriptionOpenPageData(
        state="ok",
        title=title,
        headline=headline,
        message=None,
        deeplink=deeplink,
        open_button_label=open_label,
        lead=lead,
        hint=hint,
        store_links=store_json,
        forced_platform=forced,
    )


@router.get(
    "/sub/{subscription_token}/open/{client}/data",
    response_model=SubscriptionOpenPageData,
    summary="Данные для SPA: открыть подписку в приложении (без HTML)",
)
async def subscription_open_page_data(
    request: Request,
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Доступно: {_OPEN_APPS_DOC}",
    ),
    platform: str | None = Query(
        None,
        description="Платформа для ссылок магазина: windows | android | ios | macos | linux (иначе — по UA на клиенте).",
    ),
) -> SubscriptionOpenPageData:
    app = get_subscription_open_app(client)
    if app is None:
        raise HTTPException(status_code=404, detail="unknown_client")

    user = table_select_one(session, User, filters={"token": subscription_token})
    return _build_open_page_data(
        request,
        user,
        app,
        store_platform=_normalize_store_platform(platform),
    )


@router.get(
    "/sub/{subscription_token}/open/{client}",
    summary=f"Редирект на SPA открытия клиента (client: {_OPEN_APPS_DOC})",
    response_class=RedirectResponse,
)
async def subscription_open_in_app(
    request: Request,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Доступно: {_OPEN_APPS_DOC}",
    ),
    platform: str | None = Query(
        None,
        description="Платформа для ссылок магазина: windows | android | ios | macos | linux.",
    ),
) -> RedirectResponse:
    app = get_subscription_open_app(client)
    if app is None:
        return RedirectResponse(
            url=_cabinet_redirect_url(extra_query={"unknown_client": "1"}),
            status_code=302,
        )

    url = _open_subscription_spa_url(
        request,
        subscription_token,
        client,
        platform=platform,
    )
    if _open_redirect_would_loop(request, url):
        raise HTTPException(
            status_code=503,
            detail=(
                "Откройте эту ссылку через сайт (Vite в dev или nginx в проде), а не напрямую на порт API — "
                "нужен тот же путь /sub/…/open/… на хосте с Vue. Или задайте SUBSCRIPTION_OPEN_SPA_BASE_URL."
            ),
        )
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/sub/{subscription_token}",
    summary="Подписка: text/plain, одна строка Base64 (v2rayNG, Nekoray и др.)",
    response_class=Response,
)
async def subscription_base64_by_token(
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    payload = await _subscription_payload_for_token(subscription_token, session)
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
    )


@router.get(
    "/sub/{subscription_token}/json",
    response_model=SubscriptionPayload,
    summary="Подписка (JSON): узлы, vless:// и поле subscription_base64",
)
async def subscription_json_by_token(
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> SubscriptionPayload:
    return await _subscription_payload_for_token(subscription_token, session)
