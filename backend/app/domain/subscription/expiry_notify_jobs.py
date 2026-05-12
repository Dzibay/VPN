"""Создание задач ``notify_sub_expire_*`` в таблице ``tasks`` (обрабатывает Telegram-бот).

``users.subscription_until`` — календарная дата (UTC-день, см. ``app.core.time.utc_today`` и
``user_has_active_subscription``): последний день включительно; на следующий UTC-день доступа нет.
Отдельно выравнивать время «до полуночи» не требуется — у типа DATE в БД нет компонента времени.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_today
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.expiry_notify")

_EXPIRE_NOTIFY_TYPES: tuple[str, ...] = (
    "notify_sub_expire_3d",
    "notify_sub_expire_1d",
    "notify_sub_expire_0d",
)


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
    if days_until_end == 1:
        yield "notify_sub_expire_1d"
    if days_until_end == 0:
        yield "notify_sub_expire_0d"


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


_SUB_EXPIRED_TASK_TYPE = "notify_sub_expire"


def _pending_sub_expired_keys(session: Session, user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    rows = session.execute(
        select(Task.user_id).where(
            Task.user_id.in_(user_ids),
            Task.status == "pending",
            Task.task_type == _SUB_EXPIRED_TASK_TYPE,
        ),
    ).all()
    return {int(uid) for uid, in rows}


def enqueue_subscription_expired_notification_tasks() -> int:
    """Создать ``notify_sub_expire`` для пользователей в первый UTC-день после окончания подписки.

    Условие: ``subscription_until`` = вчера по UTC (последний оплаченный день был «вчера»), есть
    ``telegram_id``. Идемпотентно: не дублирует pending-задачу того же типа.

    Вызывается вместе с ежедневным sync Xray (снятие клиентов с узлов), не из ручного enqueue sync.
    """

    today = utc_today()
    last_paid_day = today - timedelta(days=1)
    created = 0
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(User.id).where(
                    User.subscription_until == last_paid_day,
                    User.telegram_id.isnot(None),
                ),
            ).all(),
        )
        user_ids = [int(uid) for uid, in rows]
        pending_uids = _pending_sub_expired_keys(db, user_ids)
        staged: set[int] = set()
        for (user_id,) in rows:
            uid = int(user_id)
            if uid in pending_uids or uid in staged:
                continue
            db.add(
                Task(
                    task_type=_SUB_EXPIRED_TASK_TYPE,
                    user_id=uid,
                    referee_id=None,
                    bonus_days=None,
                ),
            )
            staged.add(uid)
            created += 1
        db.commit()
    if created:
        log.info(
            "Подписка истекла (notify_sub_expire): создано задач=%s "
            "(UTC-сегодня=%s, последний оплаченный день=%s, кандидатов=%s)",
            created,
            today.isoformat(),
            last_paid_day.isoformat(),
            len(rows),
        )
    else:
        log.debug(
            "notify_sub_expire: новых задач нет (UTC-сегодня=%s, last_paid_day=%s, кандидатов=%s)",
            today.isoformat(),
            last_paid_day.isoformat(),
            len(rows),
        )
    return created
