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
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

_NOTIFICATION_TYPES: tuple[str, ...] = ("notify_reg", "notify_payment")


async def list_pending_notification_tasks(
    session: AsyncSession,
) -> TelegramNotificationTasksListResponse:
    """Все невыполненные задачи типов notify_reg / notify_payment, по возрастанию created_at."""
    ur = aliased(User)
    rr = aliased(User)
    stmt = (
        select(Task, ur.telegram_id, rr.telegram_id)
        .join(ur, ur.id == Task.user_id)
        .outerjoin(rr, rr.id == Task.referee_id)
        .where(
            Task.done_at.is_(None),
            Task.task_type.in_(_NOTIFICATION_TYPES),
        )
        .order_by(Task.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    items: list[TelegramNotificationTaskItem] = []
    for task, rec_tid, ref_tid in rows:
        ttype = task.task_type
        if ttype not in _NOTIFICATION_TYPES:
            continue
        items.append(
            TelegramNotificationTaskItem(
                id=int(task.id),
                type=ttype,  # type: ignore[arg-type]
                user_id=int(task.user_id),
                referee_id=int(task.referee_id) if task.referee_id is not None else None,
                bonus_days=int(task.bonus_days) if task.bonus_days is not None else None,
                created_at=task.created_at,
                recipient_telegram_id=int(rec_tid) if rec_tid is not None else None,
                referee_telegram_id=int(ref_tid) if ref_tid is not None else None,
            ),
        )
    return TelegramNotificationTasksListResponse(tasks=items)


async def acknowledge_notification_tasks(session: AsyncSession, task_ids: list[int]) -> list[int]:
    """Проставить done_at только для подходящих id; вернуть те, что реально обновлены."""
    if not task_ids:
        return []
    now = datetime.now(timezone.utc)
    stmt = (
        update(Task)
        .where(
            Task.id.in_(task_ids),
            Task.done_at.is_(None),
            Task.task_type.in_(_NOTIFICATION_TYPES),
        )
        .values(done_at=now)
        .returning(Task.id)
    )
    res = await session.execute(stmt)
    return sorted(int(x) for x in res.scalars().all())
