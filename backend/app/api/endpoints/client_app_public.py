"""Публичные данные о клиентах подписки (скачивание / сайт), без привязки к токену."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from app.domain.subscription_open_apps import (
    get_subscription_open_app,
    list_subscription_open_app_codes,
)
from app.schemas.client_app_public import ClientAppPublicResponse

router = APIRouter(tags=["public"])

_APPS_DOC = ", ".join(list_subscription_open_app_codes())


@router.get(
    "/public/client-apps/{client_code}",
    response_model=ClientAppPublicResponse,
    summary="Публичные сведения о VPN-клиенте: наименование и ссылки на магазины приложений",
)
async def client_app_public(
    client_code: str = Path(..., description=f"Код клиента. Допустимые значения: {_APPS_DOC}"),
) -> ClientAppPublicResponse:
    app = get_subscription_open_app(client_code)
    if app is None:
        raise HTTPException(status_code=404, detail="unknown_client")
    sl = app.store_links
    links = sl.to_public_json_dict() if sl.any() else {}
    return ClientAppPublicResponse(
        client_code=client_code,
        display_name=app.display_name,
        store_links=links,
    )
