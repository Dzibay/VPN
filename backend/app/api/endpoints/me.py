"""Эндпоинты профиля по JWT без префикса /auth (/api/me/...)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.api.deps import BearerPrincipal, SessionDep, get_bearer_principal_dep
from app.models.subscription_device import SubscriptionDevice

router = APIRouter(prefix="/me", tags=["user"])


@router.delete(
    "/subscription-devices/{device_id}",
    status_code=204,
    summary="Удалить подключение",
)
async def delete_my_subscription_device(
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    device_id: int = Path(
        ...,
        ge=1,
        description="Идентификатор строки из поля id в subscription_connections (GET /api/auth/me)",
    ),
) -> None:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    row = session.get(SubscriptionDevice, device_id)
    if row is None or int(row.user_id) != int(principal.user_id):
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    session.delete(row)
