"""Эндпоинты для бэкенда Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep, require_telegram_bot_api_secret
from app.core.config import settings
from app.domain.subscription_public_base import subscription_public_base_from_setting
from app.models.user import User
from app.schemas.account import (
    TelegramAuthBody,
    TelegramProfilePatchBody,
    TelegramSubscriptionOpenClientsResponse,
    TelegramUserPropertiesUpdateResponse,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
)

router = APIRouter(prefix="/telegram", tags=["public"])


@router.get(
    "/subscription-open-clients",
    response_model=TelegramSubscriptionOpenClientsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Список VPN-клиентов для кнопок «Подключить» (тот же источник, что /api/auth/me; секрет бота)",
)
async def subscription_open_clients() -> TelegramSubscriptionOpenClientsResponse:
    base = subscription_public_base_from_setting(settings.subscription_public_base_url)
    return TelegramSubscriptionOpenClientsResponse(
        clients=build_subscription_open_client_items(),
        public_base_url=base or None,
    )


@router.patch(
    "/users/{telegram_id}",
    response_model=TelegramUserPropertiesUpdateResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary=(
        "Обновить telegram_properties пользователя (та же модель слияния, что POST /api/auth/telegram; секрет бота)"
    ),
)
async def patch_user_telegram_properties(
    telegram_id: int,
    body: TelegramProfilePatchBody,
    session: SessionDep,
) -> TelegramUserPropertiesUpdateResponse:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(
            status_code=422,
            detail="Укажите хотя бы одно поле: username, first_name, last_name, topic_id",
        )
    auth_fragment = TelegramAuthBody(telegram_id=telegram_id, **patch)

    stmt = select(User).where(User.telegram_id == telegram_id).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь с таким telegram_id не найден")

    user.telegram_properties = merge_telegram_auth_profile(
        auth_fragment,
        user.telegram_properties,
    )
    session.flush()

    return TelegramUserPropertiesUpdateResponse(
        telegram_id=int(user.telegram_id or telegram_id),
        telegram_properties=user.telegram_properties,
    )
