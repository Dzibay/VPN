"""Платежи для сценариев Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.services.telegram_service import require_user_by_telegram_id
from app.infrastructure.persistence.models.payment import Payment


async def create_pending_payment_for_telegram_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    amount: Decimal,
    months: int,
) -> Payment:
    user = await require_user_by_telegram_id(session, telegram_id)
    row = Payment(user_id=int(user.id), amount=amount, months=months, status="pending")
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def set_payment_terminal_status_for_telegram_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    payment_id: int,
    status: Literal["completed", "failed"],
) -> Payment:
    user = await require_user_by_telegram_id(session, telegram_id)
    stmt = select(Payment).where(Payment.id == payment_id).limit(1)
    res = await session.execute(stmt)
    row = res.scalar_one_or_none()
    if row is None or int(row.user_id) != int(user.id):
        raise NotFoundError("Платёж не найден для этого пользователя")
    if row.status != "pending":
        raise ConflictError(f"Платёж уже в статусе «{row.status}», изменение невозможно")
    row.status = status
    await session.flush()
    await session.refresh(row)
    return row
