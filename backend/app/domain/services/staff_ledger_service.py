"""Выборки payments и tasks для админки (manager/admin)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.staff_ledger import StaffPaymentItem, StaffTaskItem
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task


async def list_staff_payments(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[StaffPaymentItem], int]:
    total = int(await session.scalar(select(func.count()).select_from(Payment)) or 0)
    stmt = (
        select(Payment)
        .order_by(Payment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.scalars(stmt)).all())
    return [StaffPaymentItem.model_validate(r) for r in rows], total


async def list_staff_tasks(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[StaffTaskItem], int]:
    total = int(await session.scalar(select(func.count()).select_from(Task)) or 0)
    stmt = select(Task).order_by(Task.id.desc()).limit(limit).offset(offset)
    rows = list((await session.scalars(stmt)).all())
    items = [
        StaffTaskItem(
            id=int(t.id),
            type=str(t.task_type),
            user_id=int(t.user_id),
            referee_id=int(t.referee_id) if t.referee_id is not None else None,
            bonus_days=int(t.bonus_days) if t.bonus_days is not None else None,
            paid_months=int(t.paid_months) if t.paid_months is not None else None,
            status=str(t.status),
            created_at=t.created_at,
            done_at=t.done_at,
        )
        for t in rows
    ]
    return items, total
