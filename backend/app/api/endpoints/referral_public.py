"""Публичные эндпоинты реферальных ссылок (без JWT)."""

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.schemas.referral_links import ReferralTrackClickBody
from app.services.referral_link_service import increment_referral_counter_by_token

router = APIRouter(prefix="/referral", tags=["public"])


@router.post(
    "/track-click",
    status_code=204,
    summary="Регистрация перехода по реферальной ссылке на сайте (инкремент счётчика кликов)",
)
async def track_referral_click(
    body: ReferralTrackClickBody,
    session: SessionDep,
) -> Response:
    """Не раскрывает, существовал ли токен: всегда 204 при валидном теле запроса."""
    increment_referral_counter_by_token(session, body.token, "clicks")
    return Response(status_code=204)
