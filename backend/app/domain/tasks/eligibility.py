"""Условия постановки задач оповещения в ``tasks``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.persistence.models.user import User


def user_has_telegram_id(telegram_id: int | None) -> bool:
    return telegram_id is not None


async def async_user_has_telegram_id(session: AsyncSession, user_id: int) -> bool:
    tid = await session.scalar(select(User.telegram_id).where(User.id == int(user_id)))
    return user_has_telegram_id(tid)
