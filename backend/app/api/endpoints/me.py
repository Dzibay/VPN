"""Эндпоинты профиля по JWT без префикса /auth (/api/me/...)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.dependencies import BearerPrincipal, SessionDep, get_bearer_principal_dep
from app.domain.services.me_service import delete_subscription_device

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
    await delete_subscription_device(session, user_id=int(principal.user_id), device_id=device_id)
