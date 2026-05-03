"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).

Ответы ``GET/HEAD /sub/{token}``, ``GET /sub/{token}/json`` и ``GET /sub/{token}/clash`` отдают метаданные в HTTP-заголовках
в форме Happ (``subscription-userinfo``, ``profile-update-interval``, ``profile-title``, …;
см. https://www.happ.su/main/ru/dev-docs/app-management#standartnye-parametry) и тот же
формат ``subscription-userinfo`` (upload, download, total, expire), что используют
Stash / Clash Verge / v2rayNG. Подробнее: ``app.domain.subscription_userinfo``.

При исчерпании лимита устройств (``SUBSCRIPTION_MAX_DEVICES``) ответ остаётся 200 с пустым списком узлов
и текстом в заголовке ``announce``, без HTTP 403.

- GET /sub/{subscription_token}/open/{client} — 302 на ту же страницу на origin SPA (если API и сайт разъехались).
- GET /sub/{subscription_token}/open/{client}/data — JSON для попытки диплинка (Vue /sub/…/open/…); скачивание — /apps/{client}.
- Неизвестный client → 302 в кабинет.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import URL as StarletteURL
from starlette.requests import Request

from app.api.deps import ReadonlySessionDep, SessionDep
from app.core.config import settings
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.domain.subscription_public_base import site_address_to_public_origin
from app.domain.subscription_userinfo import (
    build_subscription_userinfo_header_value,
    subscription_announce_header_value,
)
from app.domain.user_traffic import user_traffic_totals
from app.domain.subscription_open_apps import (
    AppStoreLinks,
    get_subscription_open_app,
    list_subscription_open_app_codes,
)
from app.models.server import Server
from app.models.user import User
from app.schemas.subscription_open_page import SubscriptionOpenPageData
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_clash_subscription_yaml,
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)
from app.services.subscription_devices import (
    SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE,
    register_or_touch_subscription_device,
)

router = APIRouter(tags=["public"])

# Имя path-параметра не «token»: иначе Swagger UI подставляет example=token и URL выглядит как /sub/token/... .
_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE = "R7k4mN9pQ2sT5vX8yZ1aB3cD6eF0gH2j"
_SUBSCRIPTION_TOKEN_PATH = Path(
    ...,
    description="Токен подписки (поле users.token) в пути /sub/{token}/…",
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


def _resolve_public_base(_request: Request) -> str:
    return site_address_to_public_origin(settings.site_address)


def _resolve_spa_base(request: Request) -> str:
    return _resolve_public_base(request)


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


async def _subscription_payload_rows_for_resolved_user(
    session: Session,
    user: User,
    *,
    device_allowed: bool = True,
) -> tuple[SubscriptionPayload, User, list[Server]]:
    if not user_has_active_subscription(user):
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=False,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    if not device_allowed:
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=True,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    rows = await run_in_threadpool(subscription_servers_after_prometheus_sync)
    return build_subscription_payload(user, rows), user, rows


def _maybe_register_subscription_device(
    *,
    session: Session,
    request: Request,
    user: User | None,
) -> bool:
    if user is None:
        return True
    return register_or_touch_subscription_device(
        session,
        settings=settings,
        user=user,
        request=request,
    )


def _subscription_client_metadata_headers(
    session: Session,
    user: User,
    *,
    request: Request | None = None,
    device_limit_rejected: bool = False,
) -> dict[str, str]:
    """Заголовки метаданных подписки для Happ / Stash / Clash (формат Happ — нижний регистр имён)."""
    up_b, down_b, _ = user_traffic_totals(session, int(user.id))
    userinfo = build_subscription_userinfo_header_value(
        valid_until=user.subscription_until,
        upload=up_b,
        download=down_b,
        total=0,
    )
    if device_limit_rejected and user_has_active_subscription(user):
        announce_raw = SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE
    elif not user_has_active_subscription(user):
        announce_raw = "Подписка истекла — продлите подписку в личном кабинете или боте."
    else:
        announce_raw = ""
    headers: dict[str, str] = {
        "subscription-userinfo": userinfo,
        "profile-update-interval": "2",
        "profile-title": "Podorozhnik VPN",
        "support-url": "",
        "profile-web-page-url": "",
        "announce": subscription_announce_header_value(announce_raw),
        "announce-url": "",
    }
    return headers


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

    base = _resolve_public_base(request)
    suffix = (app.subscription_fetch_path_suffix or "").strip()
    subscription_url = f"{base}/sub/{user.token}{suffix}"
    deeplink = app.build_deeplink(subscription_url)
    sl: AppStoreLinks = app.store_links
    store_json = sl.to_public_json_dict() if sl.any() else None

    active = user_has_active_subscription(user)
    lead_active = lead
    lead_inactive = (
        "Подписка сейчас не активна — узлы VPN в клиенте появятся после продления. "
        "Приложение можно открыть и заранее добавить ссылку подписки — список серверов будет пустым, пока подписка не станет активной."
    )

    return SubscriptionOpenPageData(
        state="ok",
        title=title,
        headline=headline,
        message=None,
        deeplink=deeplink,
        open_button_label=open_label,
        lead=lead_active if active else lead_inactive,
        hint=hint,
        store_links=store_json,
        forced_platform=forced,
    )


@router.get(
    "/sub/{subscription_token}/open/{client}/data",
    response_model=SubscriptionOpenPageData,
    summary="Данные для SPA-страницы открытия подписки во внешнем клиенте (JSON)",
)
async def subscription_open_page_data(
    request: Request,
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Допустимые значения: {_OPEN_APPS_DOC}",
    ),
    platform: str | None = Query(
        None,
        description="Платформа для ссылок на магазины: windows, android, ios, macos, linux",
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
    summary=f"Перенаправление HTTP 302 на SPA-маршрут открытия клиента (допустимые client: {_OPEN_APPS_DOC})",
    response_class=RedirectResponse,
)
async def subscription_open_in_app(
    request: Request,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Допустимые значения: {_OPEN_APPS_DOC}",
    ),
    platform: str | None = Query(
        None,
        description="Платформа для ссылок на магазины приложений",
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
                "нужен тот же путь /sub/…/open/… на хосте с Vue. Укажите SITE_ADRESS на URL этого сайта."
            ),
        )
    return RedirectResponse(url=url, status_code=302)


@router.head(
    "/sub/{subscription_token}",
    summary="HEAD-запрос подписки: ответ без тела, только заголовки метаданных (совместимо с Happ и аналогами)",
    response_class=Response,
)
async def subscription_head_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = _maybe_register_subscription_device(session=session, request=request, user=user)
    headers = _subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    return Response(content="", media_type="text/plain; charset=utf-8", headers=headers)


@router.get(
    "/sub/{subscription_token}",
    summary="Тело подписки: text/plain, одна строка в кодировке Base64",
    response_class=Response,
)
async def subscription_base64_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = _maybe_register_subscription_device(session=session, request=request, user=user)
    payload, user, _rows = await _subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = _subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.head(
    "/sub/{subscription_token}/clash",
    summary="HEAD подписки Clash: без тела, те же заголовки метаданных",
    response_class=Response,
)
async def subscription_clash_head_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = _maybe_register_subscription_device(session=session, request=request, user=user)
    headers = _subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    return Response(content="", media_type="text/plain; charset=utf-8", headers=headers)


@router.get(
    "/sub/{subscription_token}/clash",
    summary="Подписка для Clash / FlClashX / Stash: YAML (Clash Meta), не Base64",
    response_class=Response,
)
async def subscription_clash_yaml_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = _maybe_register_subscription_device(session=session, request=request, user=user)
    _payload, user, rows = await _subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = _subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    yaml_body = build_clash_subscription_yaml(user, rows)
    return Response(
        content=yaml_body,
        media_type="text/yaml; charset=utf-8",
        headers=headers,
    )


@router.get(
    "/sub/{subscription_token}/json",
    response_model=SubscriptionPayload,
    summary="Подписка в формате JSON; метаданные дублируются в заголовках ответа",
)
async def subscription_json_by_token(
    request: Request,
    response: Response,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": subscription_token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = _maybe_register_subscription_device(session=session, request=request, user=user)
    payload, user, _rows = await _subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    for key, val in _subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    ).items():
        response.headers[key] = val
    return payload
