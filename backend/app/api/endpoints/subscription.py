"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{token}).
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.database.operations import table_select_one
from app.models.user import User
from app.schemas.users import SubscriptionPayload

router = APIRouter(tags=["subscription"])


@router.get(
    "/sub/{token}",
    response_model=SubscriptionPayload,
    summary="Конфигурация подписки по токену",
)
async def subscription_by_token(token: str, session: SessionDep) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    return SubscriptionPayload(
        valid_until=user.subscription_until,
        servers=[],
    )
