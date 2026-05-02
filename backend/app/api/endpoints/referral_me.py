"""Клиентское API: одна персональная реферальная ссылка для роли JWT user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import BearerPrincipal, SessionDep, get_bearer_principal_dep
from app.core.config import settings
from app.schemas.referral_links import ReferralMeResponse
from app.services.referral_link_service import get_or_create_user_owned_referral_link, referral_link_to_out

router = APIRouter(prefix="/referral/me", tags=["user"])


def _client_site_user_id(principal: BearerPrincipal) -> int:
    """Только аккаунт с ролью «пользователь» (JWT user), без admin/manager."""
    if principal.role != "user":
        raise HTTPException(
            status_code=403,
            detail=(
                "Персональная реферальная ссылка доступна только для учётной записи "
                "клиента (токены для сотрудников — через админ-панель)."
            ),
        )
    uid = principal.user_id
    if uid is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    return int(uid)


@router.get(
    "",
    response_model=ReferralMeResponse,
    summary="Персональная реферальная ссылка текущего пользователя",
    description=(
        "Возвращает существующую персональную ссылку или создаёт её при первом обращении "
        "(не более одной на учётную запись)."
    ),
)
async def get_my_referral_link(
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> ReferralMeResponse:
    user_id = _client_site_user_id(principal)
    try:
        row = get_or_create_user_owned_referral_link(session, user_id)
    except ValueError as e:
        msg = str(e)
        if msg == "Пользователь не найден":
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=422, detail=msg) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ReferralMeResponse(link=referral_link_to_out(row, settings))
