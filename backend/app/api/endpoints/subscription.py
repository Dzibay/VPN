"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Список узлов строится из БД и сортируется по ``servers.load_percent`` (актуализация из Prometheus —
фоновый планировщик в процессе API, по умолчанию каждые 5 минут, см. настройки
``SERVER_LOAD_PROMETHEUS_SYNC_*``).

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

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, SessionDep
from app.domain.models.subscription import SubscriptionOpenPageData, SubscriptionPayload
from app.domain.subscription_open_apps import get_subscription_open_app, list_subscription_open_app_codes
from app.domain.services.subscription_service import (
    build_clash_subscription_yaml,
    normalize_subscription_store_platform,
    subscription_build_open_page_data,
    subscription_cabinet_redirect_url,
    subscription_client_metadata_headers,
    subscription_maybe_register_device,
    subscription_open_redirect_would_loop,
    subscription_open_spa_url,
    subscription_payload_rows_for_resolved_user,
    user_by_subscription_token,
)

router = APIRouter(tags=["public"])

_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE = "R7k4mN9pQ2sT5vX8yZ1aB3cD6eF0gH2j"
_SUBSCRIPTION_TOKEN_PATH = Path(
    ...,
    description="Токен подписки (поле users.token) в пути /sub/{token}/…",
    examples=[_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE],
)

_OPEN_APPS_DOC = ", ".join(list_subscription_open_app_codes())


@router.get(
    "/sub/{subscription_token}/open/{client}/data",
    response_model=SubscriptionOpenPageData,
    summary="Данные для SPA-страницы открытия подписки во внешнем клиенте (JSON)",
)
async def subscription_open_page_data(
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

    user = user_by_subscription_token(session, subscription_token)
    return subscription_build_open_page_data(
        user,
        app,
        store_platform=normalize_subscription_store_platform(platform),
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
            url=subscription_cabinet_redirect_url(settings, extra_query={"unknown_client": "1"}),
            status_code=302,
        )

    url = subscription_open_spa_url(
        subscription_token,
        client,
        platform=platform,
        cfg=settings,
    )
    if subscription_open_redirect_would_loop(request, url):
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
    user = user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = subscription_maybe_register_device(session=session, request=request, user=user, cfg=settings)
    headers = subscription_client_metadata_headers(
        session,
        user,
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
    user = user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = subscription_maybe_register_device(session=session, request=request, user=user, cfg=settings)
    payload, user, _rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = subscription_client_metadata_headers(
        session,
        user,
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
    user = user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = subscription_maybe_register_device(session=session, request=request, user=user, cfg=settings)
    headers = subscription_client_metadata_headers(
        session,
        user,
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
    user = user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = subscription_maybe_register_device(session=session, request=request, user=user, cfg=settings)
    _payload, user, rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = subscription_client_metadata_headers(
        session,
        user,
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
    user = user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = subscription_maybe_register_device(session=session, request=request, user=user, cfg=settings)
    payload, user, _rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    for key, val in subscription_client_metadata_headers(
        session,
        user,
        device_limit_rejected=not device_ok,
    ).items():
        response.headers[key] = val
    return payload
