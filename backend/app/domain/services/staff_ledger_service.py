"""Выборки payments и tasks для админки (manager/admin)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.staff_ledger import (
    StaffCreatableTaskType,
    StaffPatchTaskBody,
    StaffPaymentItem,
    StaffPaymentsFinanceBuckets,
    StaffPaymentsFinanceSummaryResponse,
    StaffTaskItem,
)
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


async def staff_payments_finance_summary(
    session: AsyncSession,
) -> StaffPaymentsFinanceSummaryResponse:
    """Сводка для финансов: ``rpc_staff_payments_finance_summary()`` (месяцы UTC × тип оплаты)."""
    stmt = text("SELECT rpc_staff_payments_finance_summary() AS payload")
    row = (await session.execute(stmt)).one()
    raw = row.payload
    if raw is None:
        return StaffPaymentsFinanceSummaryResponse(
            months=[],
            cash=StaffPaymentsFinanceBuckets(),
            spread=StaffPaymentsFinanceBuckets(),
            grand_total="0",
            payment_count=0,
        )
    if not isinstance(raw, dict):
        raw = dict(raw)
    return StaffPaymentsFinanceSummaryResponse.model_validate(raw)


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
    items = [_staff_task_item_from_orm(t) for t in rows]
    return items, total


def _staff_task_item_from_orm(t: Task) -> StaffTaskItem:
    return StaffTaskItem(
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


async def create_staff_task(
    session: AsyncSession,
    *,
    user_id: int,
    task_type: StaffCreatableTaskType,
    referee_id: int | None,
    bonus_days: int | None,
    paid_months: int | None,
) -> StaffTaskItem:
    """Создать pending-задачу (разрешённые типы совпадают с CHECK в БД)."""
    if await session.scalar(select(User.id).where(User.id == user_id)) is None:
        raise LookupError("user_not_found")
    if referee_id is not None:
        if await session.scalar(select(User.id).where(User.id == referee_id)) is None:
            raise LookupError("referee_not_found")

    task = Task(
        task_type=task_type,
        user_id=user_id,
        referee_id=referee_id,
        bonus_days=bonus_days,
        paid_months=paid_months,
        status="pending",
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return _staff_task_item_from_orm(task)


async def update_staff_task(
    session: AsyncSession,
    task_id: int,
    patch: StaffPatchTaskBody,
) -> StaffTaskItem:
    task = await session.get(Task, task_id)
    if task is None:
        raise LookupError("task_not_found")

    data = patch.model_dump(exclude_unset=True)

    if "user_id" in data:
        uid = data["user_id"]
        if uid is not None and await session.scalar(select(User.id).where(User.id == uid)) is None:
            raise LookupError("user_not_found")
        task.user_id = uid

    if "referee_id" in data:
        rid = data["referee_id"]
        if rid is not None and await session.scalar(select(User.id).where(User.id == rid)) is None:
            raise LookupError("referee_not_found")
        task.referee_id = rid

    if "bonus_days" in data:
        task.bonus_days = data["bonus_days"]

    if "paid_months" in data:
        task.paid_months = data["paid_months"]

    if "task_type" in data:
        task.task_type = data["task_type"]

    status_in = "status" in data
    done_at_in = "done_at" in data

    if status_in:
        task.status = data["status"]

    if done_at_in:
        task.done_at = data["done_at"]
    elif status_in:
        st = data["status"]
        if st == "pending":
            task.done_at = None
        else:
            task.done_at = datetime.now(timezone.utc)

    await session.flush()
    await session.refresh(task)
    return _staff_task_item_from_orm(task)


async def delete_staff_task(session: AsyncSession, task_id: int) -> None:
    task = await session.get(Task, task_id)
    if task is None:
        raise LookupError("task_not_found")
    await session.delete(task)
    await session.flush()
