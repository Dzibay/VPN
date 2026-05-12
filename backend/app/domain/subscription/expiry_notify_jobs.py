"""Создание задач ``notify_sub_expire_*`` в таблице ``tasks`` (обрабатывает Telegram-бот).

``users.subscription_until`` — календарная дата (UTC-день, см. ``app.core.time.utc_today`` и
``user_has_active_subscription``): последний день включительно; на следующий UTC-день доступа нет.
Отдельно выравнивать время «до полуночи» не требуется — у типа DATE в БД нет компонента времени.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_today
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.expiry_notify")

_EXPIRE_NOTIFY_TYPES: tuple[str, ...] = ("notify_sub_expire_3d", "notify_sub_expire_1d")


def _pending_expire_keys_for_users(session: Session, user_ids: list[int]) -> set[tuple[int, str]]:
    """Пары (user_id, type) для уже существующих pending-задач напоминания (один запрос на прогон)."""
    if not user_ids:
        return set()
    rows = session.execute(
        select(Task.user_id, Task.task_type).where(
            Task.user_id.in_(user_ids),
            Task.status == "pending",
            Task.task_type.in_(_EXPIRE_NOTIFY_TYPES),
        ),
    ).all()
    return {(int(uid), str(tt)) for uid, tt in rows}


def _task_types_for_delta(days_until_end: int) -> Iterable[str]:
    if days_until_end == 3:
        yield "notify_sub_expire_3d"
    if days_until_end in (0, 1):
        yield "notify_sub_expire_1d"


def enqueue_subscription_expiry_notification_tasks() -> int:
    """Выбрать активных пользователей с конечной датой и telegram_id; создать недостающие задачи.

    Идемпотентно на уровне дня: повторный запуск не добавляет вторую pending-задачу того же типа.
    """

    today = utc_today()
    created = 0
    rows: list[tuple[object, object]] = []
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(User.id, User.subscription_until).where(
                    User.subscription_until.isnot(None),
                    User.subscription_until >= today,
                    User.telegram_id.isnot(None),
                ),
            ).all(),
        )
        user_ids = [int(uid) for uid, _su in rows]
        pending_keys = _pending_expire_keys_for_users(db, user_ids)
        staged: set[tuple[int, str]] = set()
        for user_id, sub_until in rows:
            delta = (sub_until - today).days
            for ttype in _task_types_for_delta(delta):
                key = (int(user_id), ttype)
                if key in pending_keys or key in staged:
                    continue
                db.add(
                    Task(
                        task_type=ttype,
                        user_id=int(user_id),
                        referee_id=None,
                        bonus_days=None,
                    ),
                )
                staged.add(key)
                created += 1
        db.commit()
    if created:
        log.info(
            "Напоминания об окончании подписки: создано задач=%s (UTC-сегодня=%s, пользователей=%s)",
            created,
            today.isoformat(),
            len(rows),
        )
    else:
        log.debug(
            "Напоминания об окончании подписки: новых задач нет (UTC-сегодня=%s, строк=%s)",
            today.isoformat(),
            len(rows),
        )
    return created
