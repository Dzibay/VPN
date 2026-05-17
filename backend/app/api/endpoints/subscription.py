"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Список узлов строится из БД: сначала узлы без ``whitelist`` (по ``servers.load_percent``),
затем с ``whitelist`` (тоже по нагрузке; актуализация из Prometheus — фоновый планировщик
в процессе API, по умолчанию каждые 5 минут, см. ``SERVER_LOAD_PROMETHEUS_SYNC_*``).
В начале списка — ``🔥 Auto (рекомендуемый)``: Xray JSON balancer ``leastPing`` по VLESS
без ``whitelist``, для которых ``include_in_auto`` (Happ), или группа ``url-test`` (Clash).
Если есть VLESS с ``whitelist`` и ``include_in_auto`` — ``📄 Auto (Белые списки)`` с тем же механизмом.
Узлы с ``include_in_auto=false`` в группы Auto не попадают (остаются отдельными строками).

Ответы ``GET /sub/{token}``, ``GET /sub/{token}/json`` отдают метаданные в HTTP-заголовках
в форме Happ (``subscription-userinfo``, ``profile-update-interval``, ``profile-title``, …;
см. https://www.happ.su/main/ru/dev-docs/app-management#standartnye-parametry) и тот же
формат ``subscription-userinfo`` (upload, download, total, expire), что используют
Stash / Clash Verge / v2rayNG. Подробнее: ``app.domain.subscription.userinfo``.

``GET /sub/{token}``: при ``User-Agent``, содержащем подстроку ``clash`` или ``hiddify`` (без учёта регистра), тело — YAML (Clash Meta);
иначе — одна строка Base64 (как ранее). Явный YAML: ``GET /sub/{token}/clash``.

При исчерпании лимита устройств (``SUBSCRIPTION_MAX_DEVICES``) ответ остаётся 200 с пустым списком узлов
и текстом в заголовке ``announce``, без HTTP 403.

- GET /sub/{subscription_token}/open/{client} — 302 на ту же страницу на origin SPA (если API и сайт разъехались).
- GET /sub/{subscription_token}/open/{client}/data — JSON для страницы открытия (Vue /sub/…/open/…: карточка клиента, диплинк, магазины); публичное имя и магазины также в GET /api/public/client-apps/{code}.
- Неизвестный client → 302 в кабинет.

Тестовые конфигурации (файл ``backend/configurations/test_configurations.json``):

- GET ``/sub/test-configurations`` — как обычная подписка: Base64 со строками ``vless://`` или YAML при User-Agent с ``clash`` / ``hiddify``.
- GET ``/sub/test-sub`` (и ``/test-sub`` в nginx) — тестовая подписка Happ (JSON array).
"""

from __future__ import annotations

from pathlib import Path as FilePath
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.config import settings
from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    apply_request_subject_from_bearer_optional,
)
from app.domain.models.subscription import SubscriptionOpenPageData, SubscriptionPayload
from app.domain.services.subscription_service import (
    subscription_build_open_page_data,
    subscription_client_metadata_headers,
    subscription_maybe_register_device,
    subscription_payload_rows_for_resolved_user,
    test_sub_client_metadata_headers,
    test_sub_payload_from_db,
    test_subscription_client_metadata_headers,
)
from app.domain.services.test_configurations_service import (
    default_test_configurations_json_path,
    load_test_configurations,
)
from app.domain.subscription.build import build_clash_subscription_yaml
from app.domain.subscription.test_config_share import (
    build_test_configs_clash_yaml,
    build_test_subscription_payload,
)
from app.domain.subscription.links import (
    normalize_subscription_store_platform,
    subscription_cabinet_redirect_url,
    subscription_open_redirect_would_loop,
    subscription_open_spa_url,
    user_by_subscription_token,
)
from app.domain.subscription.open_apps import (
    get_subscription_open_app,
    list_subscription_open_app_codes,
)

router = APIRouter(
    tags=["public"],
    dependencies=[Depends(apply_request_subject_from_bearer_optional)],
)

_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE = "R7k4mN9pQ2sT5vX8yZ1aB3cD6eF0gH2j"
_SUBSCRIPTION_TOKEN_PATH = Path(
    ...,
    description="Токен подписки (поле users.token) в пути /sub/{token}/…",
    examples=[_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE],
)

_OPEN_APPS_DOC = ", ".join(list_subscription_open_app_codes())
_APP_ROOT = FilePath(__file__).resolve().parents[2]
_GEO_DIR = _APP_ROOT / "geo"
_LOCAL_GEOIP_PATH = _GEO_DIR / "geoip.dat"
_LOCAL_GEOSITE_PATH = _GEO_DIR / "geosite.dat"


def _user_agent_requests_clash_yaml(request: Request) -> bool:
    ua = (request.headers.get("user-agent") or "").lower()
    # Clash-семейство шлёт «clash»; Hiddify Next часто без него — «hiddify» в UA.
    return "clash" in ua or "hiddify" in ua


def _read_local_geo_dat_or_503(path: FilePath, name: str) -> bytes:
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Локальный файл {name} не найден. "
                f"Положите его в {_GEO_DIR.as_posix()}/"
            ),
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Не удалось прочитать {name}") from exc


def _geo_response(body: bytes, filename: str) -> Response:
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "cache-control": "public, max-age=21600",
            "content-disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/sub/geoip.dat",
    summary="Локальный geoip.dat с домена подписки для Happ routing",
    response_class=Response,
)
async def subscription_geoip_dat() -> Response:
    body = _read_local_geo_dat_or_503(_LOCAL_GEOIP_PATH, "geoip.dat")
    return _geo_response(body, "geoip.dat")


@router.get(
    "/sub/geosite.dat",
    summary="Локальный geosite.dat с домена подписки для Happ routing",
    response_class=Response,
)
async def subscription_geosite_dat() -> Response:
    body = _read_local_geo_dat_or_503(_LOCAL_GEOSITE_PATH, "geosite.dat")
    return _geo_response(body, "geosite.dat")


def _load_test_configuration_items():
    try:
        return load_test_configurations(default_test_configurations_json_path())
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/sub/test-configurations",
    summary=(
        "Тестовая подписка из configurations/test_configurations.json: "
        "text/plain Base64 (строки vless://), либо YAML при User-Agent с подстрокой clash или hiddify"
    ),
    response_class=Response,
)
async def subscription_test_configs_get(request: Request) -> Response:
    items = _load_test_configuration_items()
    want_yaml = _user_agent_requests_clash_yaml(request)
    headers = test_subscription_client_metadata_headers(request=request)
    if want_yaml:
        yaml_body = build_test_configs_clash_yaml(items)
        return Response(
            content=yaml_body,
            media_type="text/yaml; charset=utf-8",
            headers=headers,
        )
    payload = build_test_subscription_payload(items)
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.get(
    "/sub/test-sub",
    summary="Тестовая подписка Happ: pool_rec+best_wl Auto, обычные узлы, per-WL",
    response_class=Response,
)
@router.get(
    "/test-sub",
    summary="Алиас /sub/test-sub",
    response_class=Response,
    include_in_schema=False,
)
async def test_sub_get(
    request: Request,
    session: ReadonlySessionDep,
) -> Response:
    try:
        payload = await test_sub_payload_from_db(session)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    headers = test_sub_client_metadata_headers(request=request)
    return Response(
        content=payload.subscription_base64,
        media_type=payload.subscription_media_type,
        headers=headers,
    )


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

    user = await user_by_subscription_token(session, subscription_token)
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
                "нужен тот же путь /sub/…/open/… на хосте с Vue. Укажите SITE_ADDRESS на URL этого сайта."
            ),
        )
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/sub/{subscription_token}",
    summary="Подписка: text/plain Base64, либо text/yaml при User-Agent с подстрокой clash или hiddify",
    response_class=Response,
)
async def subscription_base64_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = await user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = await subscription_maybe_register_device(
        session=session, request=request, user=user, cfg=settings,
    )
    want_yaml = _user_agent_requests_clash_yaml(request)
    headers = await subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    if want_yaml:
        _payload, user, rows = await subscription_payload_rows_for_resolved_user(
            session,
            user,
            device_allowed=device_ok,
        )
        yaml_body = build_clash_subscription_yaml(user, rows)
        return Response(
            content=yaml_body,
            media_type="text/yaml; charset=utf-8",
            headers=headers,
        )
    payload, user, _rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.get(
    "/sub/{subscription_token}/clash",
    summary="Подписка в формате Clash YAML (явный путь); метаданные в заголовках",
    response_class=Response,
)
async def subscription_clash_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    user = await user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = await subscription_maybe_register_device(
        session=session, request=request, user=user, cfg=settings,
    )
    _payload, user, rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = await subscription_client_metadata_headers(
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
    user = await user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = await subscription_maybe_register_device(
        session=session, request=request, user=user, cfg=settings,
    )
    payload, user, _rows = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
    )
    headers = await subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    for key, val in headers.items():
        response.headers[key] = val
    return payload
