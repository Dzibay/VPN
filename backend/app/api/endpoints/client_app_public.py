from fastapi import APIRouter, HTTPException, Path

from app.domain.models.client_app_public import ClientAppPublicResponse
from app.domain.services.client_app_public_service import build_client_app_public
from app.domain.subscription_open_apps import list_subscription_open_app_codes

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
    out = build_client_app_public(client_code)
    if out is None:
        raise HTTPException(status_code=404, detail="unknown_client")
    return out
