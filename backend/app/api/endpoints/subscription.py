"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Список узлов строится из БД: сначала узлы без ``whitelist`` (по ``servers.load_percent``),
затем с ``whitelist`` (тоже по нагрузке; актуализация из Prometheus — фоновый планировщик
в процессе API, по умолчанию каждые 5 минут, см. ``SERVER_LOAD_PROMETHEUS_SYNC_*``).
В начале — ``🔥 Auto (рекомендуемый)`` и при наличии WL-узлов ``📄 Auto (Белые списки)``:
Happ — JSON-балансировщики; v2raytun/v2rayNG — лучший ``vless://`` по нагрузке; Clash — ``url-test``.
Узлы с ``include_in_auto=false`` в группы Auto не попадают (остаются отдельными строками).

``GET /sub/{token}``: метаданные в HTTP-заголовках Happ; при ``clash`` / ``hiddify`` в User-Agent — YAML;
при ``happ`` — ``application/json``; иначе — ``text/plain`` Base64.
Явный YAML: ``GET /sub/{token}/clash``.

Страница «открыть в клиенте» — Vue ``/sub/{token}/open/{client}`` (nginx отдаёт SPA);
данные: ``GET /sub/{token}/open/{client}/data`` и ``GET /api/public/client-apps/{code}``.
"""

from __future__ import annotations

from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from starlette.requests import Request

from app.config import settings
from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    apply_request_subject_from_bearer_optional,
)
from app.domain.models.subscription import SubscriptionOpenPageData
from app.domain.services.subscription_service import (
    subscription_build_open_page_data,
    subscription_client_metadata_headers,
    subscription_maybe_register_device,
    subscription_payload_rows_for_resolved_user,
)
from app.domain.subscription.build import build_clash_subscription_yaml
from app.domain.subscription.client_ua import (
    subscription_user_agent_is_clash_yaml,
    subscription_user_agent_is_happ,
)
from app.domain.subscription.placeholders import build_clash_subscription_placeholder_yaml
from app.domain.subscription.links import (
    normalize_subscription_store_platform,
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


async def _subscription_by_token_response(
    request: Request,
    session: SessionDep,
    subscription_token: str,
) -> Response:
    user = await user_by_subscription_token(session, subscription_token)
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")
    device_ok = await subscription_maybe_register_device(
        session=session, request=request, user=user, cfg=settings,
    )
    want_yaml = subscription_user_agent_is_clash_yaml(request)
    happ_json = subscription_user_agent_is_happ(request)
    headers = await subscription_client_metadata_headers(
        session,
        user,
        request=request,
        device_limit_rejected=not device_ok,
    )
    if want_yaml:
        _payload, user, rows, block_reason = await subscription_payload_rows_for_resolved_user(
            session,
            user,
            device_allowed=device_ok,
            happ_json=False,
        )
        if block_reason:
            yaml_body = build_clash_subscription_placeholder_yaml(block_reason)
        else:
            yaml_body = build_clash_subscription_yaml(user, rows)
        return Response(
            content=yaml_body,
            media_type="text/yaml; charset=utf-8",
            headers=headers,
        )
    payload, user, _rows, _block_reason = await subscription_payload_rows_for_resolved_user(
        session,
        user,
        device_allowed=device_ok,
        happ_json=happ_json,
    )
    return Response(
        content=payload.subscription_base64,
        media_type=payload.subscription_media_type,
        headers=headers,
    )


@router.get(
    "/sub/{subscription_token}",
    summary="Подписка: JSON (Happ UA), Base64 (прочие), YAML (clash/hiddify UA)",
    response_class=Response,
)
async def subscription_base64_by_token(
    request: Request,
    session: SessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    return await _subscription_by_token_response(request, session, subscription_token)


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
    _payload, user, rows, block_reason = await subscription_payload_rows_for_resolved_user(
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
    if block_reason:
        yaml_body = build_clash_subscription_placeholder_yaml(block_reason)
    else:
        yaml_body = build_clash_subscription_yaml(user, rows)
    return Response(
        content=yaml_body,
        media_type="text/yaml; charset=utf-8",
        headers=headers,
    )
