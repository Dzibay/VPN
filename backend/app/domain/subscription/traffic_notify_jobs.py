"""Задачи ``notify_traffic_low`` / ``notify_traffic_over`` после батч-сбора трафика Xray."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.subscription.traffic_limit import traffic_limit_quota_applies_sql
from app.domain.tasks.dedupe import user_ids_with_task_type_ever
from app.domain.tasks.notification_task_types import NOTIFY_TRAFFIC_LOW, NOTIFY_TRAFFIC_OVER
from app.domain.user_traffic import user_traffic_totals_by_user_subquery
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.traffic_notify")

TRAFFIC_LOW_NOTIFY_THRESHOLD_BYTES = 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TrafficNotifyEnqueueResult:
    low_created: int = 0
    over_created: int = 0


def _candidate_user_ids_traffic_low(session: Session) -> list[int]:
    totals = user_traffic_totals_by_user_subquery()
    remaining = User.traffic_limit_bytes - totals.c.total_bytes
    rows = session.execute(
        select(totals.c.user_id)
        .select_from(totals.join(User, User.id == totals.c.user_id))
        .where(
            traffic_limit_quota_applies_sql(),
            User.telegram_id.isnot(None),
            totals.c.total_bytes < User.traffic_limit_bytes,
            remaining > 0,
            remaining < TRAFFIC_LOW_NOTIFY_THRESHOLD_BYTES,
        ),
    ).all()
    return [int(uid) for uid, in rows]


def _enqueue_traffic_low_tasks(session: Session) -> int:
    user_ids = _candidate_user_ids_traffic_low(session)
    already = user_ids_with_task_type_ever(session, user_ids, NOTIFY_TRAFFIC_LOW)
    created = 0
    staged: set[int] = set()
    for uid in user_ids:
        if uid in already or uid in staged:
            continue
        session.add(
            Task(
                task_type=NOTIFY_TRAFFIC_LOW,
                user_id=uid,
                referee_id=None,
                bonus_days=None,
            ),
        )
        staged.add(uid)
        created += 1
    return created


def _enqueue_traffic_over_tasks(session: Session, over_limit_user_ids: Iterable[int]) -> int:
    user_ids = [int(uid) for uid in over_limit_user_ids]
    if not user_ids:
        return 0
    rows = session.execute(
        select(User.id).where(
            User.id.in_(user_ids),
            User.telegram_id.isnot(None),
            traffic_limit_quota_applies_sql(),
        ),
    ).all()
    eligible = [int(uid) for uid, in rows]
    already = user_ids_with_task_type_ever(session, eligible, NOTIFY_TRAFFIC_OVER)
    created = 0
    staged: set[int] = set()
    for uid in eligible:
        if uid in already or uid in staged:
            continue
        session.add(
            Task(
                task_type=NOTIFY_TRAFFIC_OVER,
                user_id=uid,
                referee_id=None,
                bonus_days=None,
            ),
        )
        staged.add(uid)
        created += 1
    return created


def enqueue_traffic_notification_tasks_after_collect(
    session: Session,
    *,
    over_limit_user_ids: Iterable[int] = (),
) -> TrafficNotifyEnqueueResult:
    """Создать недостающие задачи оповещения по трафику (идемпотентно по user_id и типу)."""

    low_created = _enqueue_traffic_low_tasks(session)
    over_created = _enqueue_traffic_over_tasks(session, over_limit_user_ids)
    if low_created or over_created:
        log.info(
            "traffic notify: создано low=%s over=%s (порог low=%s байт)",
            low_created,
            over_created,
            TRAFFIC_LOW_NOTIFY_THRESHOLD_BYTES,
        )
    else:
        log.debug("traffic notify: новых задач нет")
    return TrafficNotifyEnqueueResult(
        low_created=low_created,
        over_created=over_created,
    )
