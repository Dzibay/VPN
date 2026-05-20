"""Список и подтверждение задач оповещения для Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.models.telegram_notification_tasks import (
    TelegramNotificationTaskItem,
    TelegramNotificationTasksListResponse,
)
from app.domain.tasks.notification_task_types import NOTIFICATION_TASK_TYPES
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


async def list_pending_notification_tasks(
    session: AsyncSession,
) -> TelegramNotificationTasksListResponse:
    """Все pending-задачи оповещений, по возрастанию created_at."""
    ur = aliased(User)
    rr = aliased(User)
    stmt = (
        select(Task, ur.telegram_id, rr.telegram_id)
        .join(ur, ur.id == Task.user_id)
        .outerjoin(rr, rr.id == Task.referee_id)
        .where(
            Task.status == "pending",
            Task.task_type.in_(NOTIFICATION_TASK_TYPES),
        )
        .order_by(Task.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    items: list[TelegramNotificationTaskItem] = []
    for task, rec_tid, ref_tid in rows:
        ttype = task.task_type
        if ttype not in NOTIFICATION_TASK_TYPES:
            continue
        items.append(
            TelegramNotificationTaskItem(
                id=int(task.id),
                type=ttype,  # type: ignore[arg-type]
                user_id=int(task.user_id),
                referee_id=int(task.referee_id) if task.referee_id is not None else None,
                bonus_days=int(task.bonus_days) if task.bonus_days is not None else None,
                paid_months=int(task.paid_months) if task.paid_months is not None else None,
                created_at=task.created_at,
                recipient_telegram_id=int(rec_tid) if rec_tid is not None else None,
                referee_telegram_id=int(ref_tid) if ref_tid is not None else None,
            ),
        )
    return TelegramNotificationTasksListResponse(tasks=items)


async def acknowledge_notification_tasks(session: AsyncSession, task_ids: list[int]) -> list[int]:
    completed_ids, _ = await acknowledge_notification_tasks_with_statuses(
        session,
        completed_task_ids=task_ids,
        failed_task_ids=[],
    )
    return completed_ids


async def acknowledge_notification_tasks_with_statuses(
    session: AsyncSession,
    *,
    completed_task_ids: list[int],
    failed_task_ids: list[int],
) -> tuple[list[int], list[int]]:
    """Обновить status для pending-задач; вернуть реально обновлённые completed/failed id."""

    def _unique_positive(ids: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for x in ids:
            if x > 0 and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    completed_ids = _unique_positive(completed_task_ids)
    failed_ids = _unique_positive(failed_task_ids)
    failed_ids = [x for x in failed_ids if x not in set(completed_ids)]
    now = datetime.now(timezone.utc)

    async def _update(ids: list[int], status: str) -> list[int]:
        if not ids:
            return []
        stmt = (
            update(Task)
            .where(
                Task.id.in_(ids),
                Task.status == "pending",
                Task.task_type.in_(NOTIFICATION_TASK_TYPES),
            )
            .values(status=status, done_at=now)
            .returning(Task.id)
        )
        res = await session.execute(stmt)
        return sorted(int(x) for x in res.scalars().all())

    updated_completed = await _update(completed_ids, "completed")
    updated_failed = await _update(failed_ids, "failed")
    return updated_completed, updated_failed
