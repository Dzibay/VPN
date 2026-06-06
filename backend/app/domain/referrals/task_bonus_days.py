"""Агрегаты бонусных дней рефералки по таблице ``tasks`` (``notify_ref_pay``, ``notify_payment``)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


async def sum_referral_bonus_days_pending_activation(
    session: AsyncSession,
    *,
    user_id: int,
) -> int:
    """Сумма ``bonus_days`` из ``notify_ref_pay`` пользователя после его последней ``notify_payment``.

    Не учитываются задачи с ``referral_bonus_applied=true`` (мгновенное зачисление на подписку).

    Если задач ``notify_payment`` ещё не было, суммируются все подходящие ``notify_ref_pay`` этого
    ``user_id`` — до первой оплаты накопленные бонусы ещё не применялись к подписке.
    """
    last_payment_at = await _last_notify_payment_created_at(session, user_id=int(user_id))

    sum_stmt = select(func.coalesce(func.sum(Task.bonus_days), 0)).where(
        Task.user_id == int(user_id),
        Task.task_type == "notify_ref_pay",
        Task.referral_bonus_applied.is_(False),
    )
    if last_payment_at is not None:
        sum_stmt = sum_stmt.where(Task.created_at > last_payment_at)

    total = (await session.scalars(sum_stmt)).first()
    return int(total or 0)


async def _last_notify_payment_created_at(
    session: AsyncSession,
    *,
    user_id: int,
):
    stmt = (
        select(Task.created_at)
        .where(
            Task.user_id == int(user_id),
            Task.task_type == "notify_payment",
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).first()


async def list_pending_referral_bonus_pay_tasks(
    session: AsyncSession,
    *,
    user_id: int,
) -> list[Task]:
    """``notify_ref_pay`` с незачислёнными бонусными днями (та же выборка, что для pending-суммы)."""
    last_payment_at = await _last_notify_payment_created_at(session, user_id=user_id)
    stmt = select(Task).where(
        Task.user_id == int(user_id),
        Task.task_type == "notify_ref_pay",
        Task.referral_bonus_applied.is_(False),
    )
    if last_payment_at is not None:
        stmt = stmt.where(Task.created_at > last_payment_at)
    return list((await session.scalars(stmt)).all())


async def apply_pending_referral_bonus_days_to_subscription(
    session: AsyncSession,
    user: User,
) -> int:
    """Зачислить накопленные бонусные дни на ``subscription_until`` и пометить задачи как выданные.

    Возвращает число зачисленных дней (0, если нечего зачислять).
    """
    tasks = await list_pending_referral_bonus_pay_tasks(session, user_id=int(user.id))
    if not tasks:
        return 0

    total_days = sum(int(t.bonus_days or 0) for t in tasks)
    if total_days <= 0:
        return 0

    from app.domain.services.payment_service import extend_subscription_until

    user.subscription_until = extend_subscription_until(
        user.subscription_until,
        days=total_days,
    )
    for task in tasks:
        task.referral_bonus_applied = True
    return total_days


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


async def sum_referral_bonus_days_received_immediately(
    session: AsyncSession,
    *,
    user_id: int,
) -> int:
    """Сумма ``bonus_days`` из ``notify_ref_pay`` с мгновенным зачислением на подписку."""
    sum_stmt = select(func.coalesce(func.sum(Task.bonus_days), 0)).where(
        Task.user_id == int(user_id),
        Task.task_type == "notify_ref_pay",
        Task.referral_bonus_applied.is_(True),
    )
    total = (await session.scalars(sum_stmt)).first()
    return int(total or 0)
