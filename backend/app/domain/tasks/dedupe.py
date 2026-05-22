"""Идемпотентность при автоматическом создании записей в ``tasks``.

* **Москва, календарный день** — планировщики могут перезапускаться в тот же день после
  ``completed`` (``notify_sub_expire_*``, ``notify_sub_expire``, ``notify_sub_expired_7d``).
* **Навсегда по user_id (+ type)** — одно уведомление на пользователя за всё время
  (``notify_traffic_*``, ``notify_reg_1h_*``).
* **Навсегда по (owner, referee)** — ``notify_ref_reg``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.time import moscow_day_bounds_utc
from app.domain.tasks.notification_task_types import NOTIFY_REF_REG
from app.infrastructure.persistence.models.task import Task


def user_ids_with_task_type_on_moscow_day(
    session: Session,
    user_ids: list[int],
    task_type: str,
    *,
    today: date,
) -> set[int]:
    if not user_ids:
        return set()
    day_start_utc, day_end_utc = moscow_day_bounds_utc(today)
    rows = session.execute(
        select(Task.user_id).where(
            Task.user_id.in_(user_ids),
            Task.task_type == task_type,
            Task.created_at >= day_start_utc,
            Task.created_at < day_end_utc,
        ),
    ).all()
    return {int(uid) for uid, in rows}


def user_task_type_keys_on_moscow_day(
    session: Session,
    user_ids: list[int],
    task_types: Iterable[str],
    *,
    today: date,
) -> set[tuple[int, str]]:
    types = tuple(task_types)
    if not user_ids or not types:
        return set()
    day_start_utc, day_end_utc = moscow_day_bounds_utc(today)
    rows = session.execute(
        select(Task.user_id, Task.task_type).where(
            Task.user_id.in_(user_ids),
            Task.task_type.in_(types),
            Task.created_at >= day_start_utc,
            Task.created_at < day_end_utc,
        ),
    ).all()
    return {(int(uid), str(tt)) for uid, tt in rows}


def user_ids_with_task_type_ever(
    session: Session,
    user_ids: list[int],
    task_type: str,
) -> set[int]:
    if not user_ids:
        return set()
    rows = session.execute(
        select(Task.user_id).where(
            Task.user_id.in_(user_ids),
            Task.task_type == task_type,
        ),
    ).all()
    return {int(uid) for uid, in rows}


def user_ids_with_any_task_type_ever(
    session: Session,
    user_ids: list[int],
    task_types: Iterable[str],
) -> set[int]:
    types = tuple(task_types)
    if not user_ids or not types:
        return set()
    rows = session.execute(
        select(Task.user_id).where(
            Task.user_id.in_(user_ids),
            Task.task_type.in_(types),
        ),
    ).all()
    return {int(uid) for uid, in rows}


async def referee_ids_with_notify_ref_reg_for_owner(
    session: AsyncSession,
    owner_id: int,
    referee_ids: list[int],
) -> set[int]:
    """referee_id, для которых у ``owner_id`` уже есть ``notify_ref_reg`` (любой status)."""
    if not referee_ids:
        return set()
    rows = await session.execute(
        select(Task.referee_id).where(
            Task.user_id == int(owner_id),
            Task.task_type == NOTIFY_REF_REG,
            Task.referee_id.in_(referee_ids),
        ),
    )
    return {int(rid) for rid, in rows.all() if rid is not None}
