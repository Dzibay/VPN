"""Канал доставки задачи оповещения (``tasks.delivery_channel``)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.user import User

TASK_DELIVERY_TELEGRAM = "telegram"
TASK_DELIVERY_WEBSITE = "website"
TASK_DELIVERY_EMAIL = "email"

TASK_DELIVERY_CHANNELS: frozenset[str] = frozenset(
    {
        TASK_DELIVERY_TELEGRAM,
        TASK_DELIVERY_WEBSITE,
        TASK_DELIVERY_EMAIL,
    },
)

TASK_DELIVERY_CHANNEL_LABELS: dict[str, str] = {
    TASK_DELIVERY_TELEGRAM: "Telegram",
    TASK_DELIVERY_WEBSITE: "Сайт (ЛК)",
    TASK_DELIVERY_EMAIL: "Email",
}


def delivery_channel_for_user(user: User) -> str:
    """Выбрать канал по данным пользователя.

    Приоритет: Telegram → подтверждённый email → сайт (аккаунт без TG и без verified email).
    """
    if user.telegram_id is not None:
        return TASK_DELIVERY_TELEGRAM
    mail = (user.email or "").strip()
    if mail and user.email_verified_at is not None:
        return TASK_DELIVERY_EMAIL
    return TASK_DELIVERY_WEBSITE


async def async_delivery_channel_for_user(session: AsyncSession, user_id: int) -> str:
    user = await session.get(User, int(user_id))
    if user is None:
        return TASK_DELIVERY_WEBSITE
    return delivery_channel_for_user(user)


def normalize_delivery_channel(raw: str | None) -> str:
    channel = (raw or TASK_DELIVERY_TELEGRAM).strip()
    if channel not in TASK_DELIVERY_CHANNELS:
        return TASK_DELIVERY_TELEGRAM
    return channel
