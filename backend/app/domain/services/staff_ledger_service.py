"""Выборки payments и tasks для админки (manager/admin)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.time import utc_now
from app.domain.tenant.admin_project_scope import apply_project_scope, rpc_project_params
from app.domain.models.staff_ledger import (
    StaffCreatableTaskType,
    StaffCreateAllTaskTypesResponse,
    StaffCreateTributePaymentResponse,
    StaffPatchTaskBody,
    StaffPaymentItem,
    StaffPaymentsFinanceBuckets,
    StaffPaymentsFinanceSummaryResponse,
    StaffTaskItem,
)
from app.domain.services.payment_service import create_staff_manual_payment
from app.domain.list_sort import SortDir, order_clause
from app.domain.tasks.delivery_channel import delivery_channel_for_user
from app.domain.tasks.notification_task_types import (
    NOTIFICATION_TASK_TYPES,
    NOTIFY_PAYMENT,
    NOTIFY_REF_PAY,
    NOTIFY_REF_REG,
)
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


async def staff_payments_finance_summary(
    session: AsyncSession,
    *,
    granularity: Literal["month", "day"] = "month",
    date_from: date | None = None,
    date_to: date | None = None,
) -> StaffPaymentsFinanceSummaryResponse:
    """Сводка для финансов: monthly или daily RPC (UTC × тип оплаты)."""
    rpc_name = (
        "rpc_staff_payments_finance_summary_daily"
        if granularity == "day"
        else "rpc_staff_payments_finance_summary"
    )
    stmt = text(f"SELECT {rpc_name}(:p_from, :p_to, :p_project_id) AS payload")
    row = (
        await session.execute(
            stmt,
            rpc_project_params({"p_from": date_from, "p_to": date_to}),
        )
    ).one()
    raw = row.payload
    if raw is None:
        return StaffPaymentsFinanceSummaryResponse(
            months=[],
            days=[],
            cash=StaffPaymentsFinanceBuckets(),
            cash_gross=StaffPaymentsFinanceBuckets(),
            spread=StaffPaymentsFinanceBuckets(),
            spread_gross=StaffPaymentsFinanceBuckets(),
            grand_total="0",
            grand_total_gross="0",
            payment_count=0,
        )
    if not isinstance(raw, dict):
        raw = dict(raw)
    parsed = StaffPaymentsFinanceSummaryResponse.model_validate(raw)
    if granularity == "day":
        return parsed.model_copy(
            update={
                "months": [],
                "spread": StaffPaymentsFinanceBuckets(),
                "spread_gross": StaffPaymentsFinanceBuckets(),
            },
        )
    return parsed.model_copy(update={"days": []})


async def create_staff_manual_payment_record(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    months: int,
    amount_rub: Decimal,
    payment_kind: Literal["subscription", "one_time"],
    created_at: datetime | None = None,
) -> StaffCreateTributePaymentResponse:
    """Ручной платёж в админке: provider=manual, продление как после оплаты."""
    row = await create_staff_manual_payment(
        session,
        settings,
        user_id=int(user_id),
        months=int(months),
        amount=amount_rub,
        payment_kind=payment_kind,
        created_at=created_at,
    )
    return StaffCreateTributePaymentResponse(
        payment=StaffPaymentItem.model_validate(row),
        ok=True,
        event=None,
        duplicate=False,
    )


_STAFF_PAYMENT_SORT_KEYS = frozenset({
    "id",
    "user_id",
    "amount",
    "net_amount",
    "months",
    "provider",
    "payment_kind",
    "created_at",
})

_STAFF_TASK_SORT_KEYS = frozenset({
    "id",
    "type",
    "user_id",
    "referee_id",
    "bonus_days",
    "early_payment_bonus_days",
    "paid_months",
    "delivery_channel",
    "status",
    "created_at",
    "done_at",
})


def _payment_list_order_by(sort_by: str | None, sort_dir: SortDir):
    if sort_by is None or sort_by not in _STAFF_PAYMENT_SORT_KEYS:
        return (Payment.id.desc(),)
    columns = {
        "id": Payment.id,
        "user_id": Payment.user_id,
        "amount": Payment.amount,
        "net_amount": Payment.net_amount,
        "months": Payment.months,
        "provider": Payment.provider,
        "payment_kind": Payment.payment_kind,
        "created_at": Payment.created_at,
    }
    primary = columns[sort_by]
    clauses = [order_clause(primary, sort_dir)]
    if sort_by != "id":
        clauses.append(Payment.id.desc())
    return tuple(clauses)


def _task_list_order_by(sort_by: str | None, sort_dir: SortDir):
    if sort_by is None or sort_by not in _STAFF_TASK_SORT_KEYS:
        return (Task.id.desc(),)
    columns = {
        "id": Task.id,
        "type": Task.task_type,
        "user_id": Task.user_id,
        "referee_id": Task.referee_id,
        "bonus_days": Task.bonus_days,
        "early_payment_bonus_days": Task.early_payment_bonus_days,
        "paid_months": Task.paid_months,
        "delivery_channel": Task.delivery_channel,
        "status": Task.status,
        "created_at": Task.created_at,
        "done_at": Task.done_at,
    }
    primary = columns[sort_by]
    clauses = [order_clause(primary, sort_dir)]
    if sort_by != "id":
        clauses.append(Task.id.desc())
    return tuple(clauses)


async def list_staff_payments(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    user_id: int | None = None,
    sort_by: str | None = None,
    sort_dir: SortDir = "asc",
) -> tuple[list[StaffPaymentItem], int]:
    order_by = _payment_list_order_by(sort_by, sort_dir)
    if user_id is None:
        count_stmt = select(func.count()).select_from(Payment)
        stmt = select(Payment).order_by(*order_by).limit(limit).offset(offset)
    else:
        count_stmt = select(func.count()).select_from(Payment).where(Payment.user_id == user_id)
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
    count_stmt = apply_project_scope(count_stmt, Payment)
    stmt = apply_project_scope(stmt, Payment)
    total = int(await session.scalar(count_stmt) or 0)
    rows = list((await session.scalars(stmt)).all())
    return [StaffPaymentItem.model_validate(r) for r in rows], total


async def staff_delete_payments_by_ids(
    session: AsyncSession,
    *,
    ids: list[int],
) -> int:
    uniq_ids = sorted({int(v) for v in ids if int(v) > 0})
    if not uniq_ids:
        return 0
    res = await session.execute(delete(Payment).where(Payment.id.in_(uniq_ids)))
    await session.commit()
    return int(res.rowcount or 0)


async def list_staff_tasks(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    user_id: int | None = None,
    sort_by: str | None = None,
    sort_dir: SortDir = "asc",
) -> tuple[list[StaffTaskItem], int]:
    order_by = _task_list_order_by(sort_by, sort_dir)
    if user_id is None:
        count_stmt = select(func.count()).select_from(Task)
        stmt = select(Task).order_by(*order_by).limit(limit).offset(offset)
    else:
        count_stmt = select(func.count()).select_from(Task).where(Task.user_id == user_id)
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
    count_stmt = apply_project_scope(count_stmt, Task)
    stmt = apply_project_scope(stmt, Task)
    total = int(await session.scalar(count_stmt) or 0)
    rows = list((await session.scalars(stmt)).all())
    items = [_staff_task_item_from_orm(t) for t in rows]
    return items, total


async def get_staff_task(session: AsyncSession, task_id: int) -> StaffTaskItem | None:
    stmt = select(Task).where(Task.id == int(task_id)).limit(1)
    stmt = apply_project_scope(stmt, Task)
    task = (await session.scalars(stmt)).first()
    if task is None:
        return None
    return _staff_task_item_from_orm(task)


async def _get_staff_task_orm(session: AsyncSession, task_id: int) -> Task | None:
    stmt = select(Task).where(Task.id == int(task_id)).limit(1)
    stmt = apply_project_scope(stmt, Task)
    return (await session.scalars(stmt)).first()


async def _get_staff_user_orm(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == int(user_id)).limit(1)
    stmt = apply_project_scope(stmt, User)
    return (await session.scalars(stmt)).first()


def _staff_task_item_from_orm(t: Task) -> StaffTaskItem:
    return StaffTaskItem(
        id=int(t.id),
        type=str(t.task_type),
        user_id=int(t.user_id),
        referee_id=int(t.referee_id) if t.referee_id is not None else None,
        bonus_days=int(t.bonus_days) if t.bonus_days is not None else None,
        early_payment_bonus_days=(
            int(t.early_payment_bonus_days) if t.early_payment_bonus_days is not None else None
        ),
        paid_months=int(t.paid_months) if t.paid_months is not None else None,
        delivery_channel=str(t.delivery_channel),
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
    early_payment_bonus_days: int | None,
    paid_months: int | None,
) -> StaffTaskItem:
    """Создать pending-задачу (разрешённые типы совпадают с CHECK в БД)."""
    recipient = await _get_staff_user_orm(session, int(user_id))
    if recipient is None:
        raise LookupError("user_not_found")
    if referee_id is not None:
        referee = await _get_staff_user_orm(session, int(referee_id))
        if referee is None or int(referee.project_id) != int(recipient.project_id):
            raise LookupError("referee_not_found")

    task = Task(
        project_id=int(recipient.project_id),
        task_type=task_type,
        user_id=user_id,
        referee_id=referee_id,
        bonus_days=bonus_days,
        early_payment_bonus_days=early_payment_bonus_days,
        paid_months=paid_months,
        status="pending",
        delivery_channel=delivery_channel_for_user(recipient),
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return _staff_task_item_from_orm(task)


async def create_all_staff_task_types(
    session: AsyncSession,
    *,
    user_id: int,
    referee_id: int | None,
    bonus_days: int,
    early_payment_bonus_days: int,
    paid_months: int,
) -> StaffCreateAllTaskTypesResponse:
    """Создать по одной pending-задаче каждого разрешённого типа для пользователя."""
    recipient = await _get_staff_user_orm(session, int(user_id))
    if recipient is None:
        raise LookupError("user_not_found")
    if referee_id is not None:
        referee = await _get_staff_user_orm(session, int(referee_id))
        if referee is None or int(referee.project_id) != int(recipient.project_id):
            raise LookupError("referee_not_found")

    delivery_channel = delivery_channel_for_user(recipient)
    tasks: list[Task] = []
    for task_type in NOTIFICATION_TASK_TYPES:
        task = Task(
            project_id=int(recipient.project_id),
            task_type=task_type,
            user_id=int(user_id),
            referee_id=referee_id if task_type in (NOTIFY_REF_REG, NOTIFY_REF_PAY) else None,
            bonus_days=bonus_days if task_type in (NOTIFY_REF_REG, NOTIFY_REF_PAY) else None,
            early_payment_bonus_days=(
                early_payment_bonus_days if task_type == NOTIFY_PAYMENT else None
            ),
            paid_months=paid_months if task_type == NOTIFY_PAYMENT else None,
            status="pending",
            delivery_channel=delivery_channel,
        )
        session.add(task)
        tasks.append(task)

    await session.flush()
    for task in tasks:
        await session.refresh(task)

    items = [_staff_task_item_from_orm(task) for task in tasks]
    return StaffCreateAllTaskTypesResponse(created_count=len(items), items=items)


async def update_staff_task(
    session: AsyncSession,
    task_id: int,
    patch: StaffPatchTaskBody,
) -> StaffTaskItem:
    task = await _get_staff_task_orm(session, task_id)
    if task is None:
        raise LookupError("task_not_found")

    data = patch.model_dump(exclude_unset=True)

    if "user_id" in data:
        uid = data["user_id"]
        if uid is not None:
            recipient = await _get_staff_user_orm(session, int(uid))
            if recipient is None:
                raise LookupError("user_not_found")
            task.project_id = int(recipient.project_id)
        task.user_id = uid

    if "referee_id" in data:
        rid = data["referee_id"]
        if rid is not None:
            referee = await _get_staff_user_orm(session, int(rid))
            if referee is None or int(referee.project_id) != int(task.project_id):
                raise LookupError("referee_not_found")
        task.referee_id = rid

    if "bonus_days" in data:
        task.bonus_days = data["bonus_days"]

    if "early_payment_bonus_days" in data:
        task.early_payment_bonus_days = data["early_payment_bonus_days"]

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
            task.done_at = utc_now()

    await session.flush()
    await session.refresh(task)
    return _staff_task_item_from_orm(task)


async def delete_staff_task(session: AsyncSession, task_id: int) -> None:
    task = await _get_staff_task_orm(session, task_id)
    if task is None:
        raise LookupError("task_not_found")
    await session.delete(task)
    await session.flush()
