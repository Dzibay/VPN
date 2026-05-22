"""Задачи ``notify_reg_1h_*`` в таблице ``tasks`` (~1 ч после регистрации, Telegram-бот)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.tasks.dedupe import user_ids_with_any_task_type_ever
from app.domain.tasks.notification_task_types import (
    NOTIFY_REG_1H_HAS_TRAFFIC,
    NOTIFY_REG_1H_NO_TRAFFIC,
    POST_REGISTRATION_NOTIFY_TYPES,
)
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic

log = logging.getLogger("app.users.post_registration_notify")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _users_with_traffic(session: Session, user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    rows = session.execute(
        select(UserServerTraffic.user_id)
        .where(
            UserServerTraffic.user_id.in_(user_ids),
            (UserServerTraffic.up_bytes + UserServerTraffic.down_bytes) > 0,
        )
        .distinct(),
    ).all()
    return {int(uid) for uid, in rows}


def enqueue_post_registration_notification_tasks() -> int:
    """Создать ``notify_reg_1h_has_traffic`` или ``notify_reg_1h_no_traffic`` для новых пользователей.

    Условия: ``registered_at`` не старше окна lookback, прошло не меньше delay с регистрации,
    есть ``telegram_id``, ещё нет задачи post-reg. Идемпотентно по user_id.
    """

    now = _utc_now()
    delay = timedelta(hours=float(settings.post_registration_notify_delay_hours))
    lookback = timedelta(minutes=int(settings.post_registration_notify_lookback_minutes))
    cutoff = now - delay
    window_start = cutoff - lookback

    created = 0
    with SessionLocal() as db:
        filters = [
            User.registered_at.isnot(None),
            User.registered_at <= cutoff,
            User.telegram_id.isnot(None),
        ]
        if not settings.post_registration_notify_include_backlog:
            filters.append(User.registered_at > window_start)

        rows = list(db.execute(select(User.id).where(*filters)).all())
        user_ids = [int(uid) for uid, in rows]
        already = user_ids_with_any_task_type_ever(db, user_ids, POST_REGISTRATION_NOTIFY_TYPES)
        candidates = [uid for uid in user_ids if uid not in already]
        with_traffic = _users_with_traffic(db, candidates)

        staged: set[int] = set()
        for uid in candidates:
            if uid in staged:
                continue
            task_type = NOTIFY_REG_1H_HAS_TRAFFIC if uid in with_traffic else NOTIFY_REG_1H_NO_TRAFFIC
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
            "post-reg notify: создано задач=%s (cutoff=%s, window_start=%s, кандидатов=%s)",
            created,
            cutoff.isoformat(),
            window_start.isoformat() if not settings.post_registration_notify_include_backlog else None,
            len(candidates),
        )
    else:
        log.debug(
            "post-reg notify: новых задач нет (cutoff=%s, строк=%s)",
            cutoff.isoformat(),
            len(rows),
        )
    return created
