"""Создание задач ``notify_sub_expire_*`` в таблице ``tasks`` (обрабатывает Telegram-бот).

``users.subscription_until`` — последний календарный день доступа по Москве (см.
``moscow_today`` и ``subscription_calendar_active``). Планировщик ставит задачи в
``subscription_expiry_notify_hour_local`` / ``_minute_local`` — по Europe/Moscow.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import moscow_today
from app.domain.tasks.notification_task_types import (
    NOTIFY_SUB_EXPIRE,
    NOTIFY_SUB_EXPIRE_0D,
    NOTIFY_SUB_EXPIRE_1D,
    NOTIFY_SUB_EXPIRE_3D,
    NOTIFY_SUB_EXPIRED_7D,
    SUBSCRIPTION_EXPIRY_NOTIFY_TYPES,
)
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.expiry_notify")


def _pending_expire_keys_for_users(session: Session, user_ids: list[int]) -> set[tuple[int, str]]:
    """Пары (user_id, type) для уже существующих pending-задач напоминания (один запрос на прогон)."""
    if not user_ids:
        return set()
    rows = session.execute(
        select(Task.user_id, Task.task_type).where(
            Task.user_id.in_(user_ids),
            Task.status == "pending",
            Task.task_type.in_(SUBSCRIPTION_EXPIRY_NOTIFY_TYPES),
        ),
    ).all()
    return {(int(uid), str(tt)) for uid, tt in rows}


def _task_types_for_delta(days_until_end: int) -> Iterable[str]:
    if days_until_end == 3:
        yield NOTIFY_SUB_EXPIRE_3D
    if days_until_end == 1:
        yield NOTIFY_SUB_EXPIRE_1D
    if days_until_end == 0:
        yield NOTIFY_SUB_EXPIRE_0D


def enqueue_subscription_expiry_notification_tasks() -> int:
    """Выбрать активных пользователей с конечной датой и telegram_id; создать недостающие задачи.

    Идемпотентно на уровне дня: повторный запуск не добавляет вторую pending-задачу того же типа.
    """

    today = moscow_today()
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
            "Напоминания об окончании подписки: создано задач=%s (МСК-сегодня=%s, пользователей=%s)",
            created,
            today.isoformat(),
            len(rows),
        )
    else:
        log.debug(
            "Напоминания об окончании подписки: новых задач нет (МСК-сегодня=%s, строк=%s)",
            today.isoformat(),
            len(rows),
        )
    return created


def _user_not_registered_on_moscow_day(today: date):
    """Пользователи, у которых календарный день ``registered_at`` по Москве ≠ ``today`` (null — ок)."""
    reg_moscow_day = cast(func.timezone("Europe/Moscow", User.registered_at), Date)
    return or_(User.registered_at.is_(None), reg_moscow_day != today)


def _pending_sub_expired_keys(
    session: Session,
    user_ids: list[int],
    task_type: str,
) -> set[int]:
    if not user_ids:
        return set()
    rows = session.execute(
        select(Task.user_id).where(
            Task.user_id.in_(user_ids),
            Task.status == "pending",
            Task.task_type == task_type,
        ),
    ).all()
    return {int(uid) for uid, in rows}


def _enqueue_sub_expired_notification_tasks(
    *,
    days_after_last_paid: int,
    task_type: str,
    skip_registered_today: bool,
) -> int:
    """Задача оповещения после окончания подписки (``subscription_until`` = today − N дней по Москве)."""

    today = moscow_today()
    last_paid_day = today - timedelta(days=days_after_last_paid)
    created = 0
    with SessionLocal() as db:
        filters = [
            User.subscription_until == last_paid_day,
            User.telegram_id.isnot(None),
        ]
        if skip_registered_today:
            filters.append(_user_not_registered_on_moscow_day(today))
        rows = list(db.execute(select(User.id).where(*filters)).all())
        user_ids = [int(uid) for uid, in rows]
        pending_uids = _pending_sub_expired_keys(db, user_ids, task_type)
        staged: set[int] = set()
        for (user_id,) in rows:
            uid = int(user_id)
            if uid in pending_uids or uid in staged:
                continue
            db.add(
                Task(
                    task_type=task_type,
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
            "%s: создано задач=%s (МСК-сегодня=%s, последний оплаченный день=%s, кандидатов=%s)",
            task_type,
            created,
            today.isoformat(),
            last_paid_day.isoformat(),
            len(rows),
        )
    else:
        log.debug(
            "%s: новых задач нет (МСК-сегодня=%s, last_paid_day=%s, кандидатов=%s)",
            task_type,
            today.isoformat(),
            last_paid_day.isoformat(),
            len(rows),
        )
    return created


def enqueue_subscription_expired_notification_tasks() -> int:
    """Создать ``notify_sub_expire`` в первый день по Москве после окончания подписки.

    Условие: ``subscription_until`` = вчера по Москве, есть ``telegram_id``, день
    ``registered_at`` (МСК) не совпадает с днём проверки.
    """

    return _enqueue_sub_expired_notification_tasks(
        days_after_last_paid=1,
        task_type=NOTIFY_SUB_EXPIRE,
        skip_registered_today=True,
    )


def enqueue_subscription_expired_7d_notification_tasks() -> int:
    """Создать ``notify_sub_expired_7d``, если подписка закончилась 7 календарных дней назад (МСК)."""

    return _enqueue_sub_expired_notification_tasks(
        days_after_last_paid=7,
        task_type=NOTIFY_SUB_EXPIRED_7D,
        skip_registered_today=False,
    )
