"""Агрегаты бонусных дней рефералки по таблице ``tasks`` (``notify_ref_pay``, ``notify_payment``)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.task import Task


async def sum_referral_bonus_days_pending_activation(
    session: AsyncSession,
    *,
    user_id: int,
) -> int:
    """Сумма ``bonus_days`` из ``notify_ref_pay`` пользователя после его последней ``notify_payment``.

    Если задач ``notify_payment`` ещё не было, суммируются все ``notify_ref_pay`` этого
    ``user_id`` — до первой оплаты накопленные бонусы ещё не применялись к подписке.
    """
    last_payment_at_stmt = (
        select(Task.created_at)
        .where(
            Task.user_id == int(user_id),
            Task.task_type == "notify_payment",
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    last_payment_at = (await session.scalars(last_payment_at_stmt)).first()

    sum_stmt = select(func.coalesce(func.sum(Task.bonus_days), 0)).where(
        Task.user_id == int(user_id),
        Task.task_type == "notify_ref_pay",
    )
    if last_payment_at is not None:
        sum_stmt = sum_stmt.where(Task.created_at > last_payment_at)

    total = (await session.scalars(sum_stmt)).first()
    return int(total or 0)


async def sum_referral_bonus_days_received_via_notify_payment(
    session: AsyncSession,
    *,
    user_id: int,
) -> int:
    """Сумма ``bonus_days`` по всем задачам ``notify_payment`` пользователя (уже учтённые при оплатах)."""
    sum_stmt = select(func.coalesce(func.sum(Task.bonus_days), 0)).where(
        Task.user_id == int(user_id),
        Task.task_type == "notify_payment",
    )
    total = (await session.scalars(sum_stmt)).first()
    return int(total or 0)
