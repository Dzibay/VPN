"""
Персональный лимит трафика пользователя (``users.traffic_limit_bytes``).

- ``NULL`` — без лимита (обычно после оплаты).
- Число — потолок накопленного up+down (байты) по всем узлам; при ``used >= limit`` доступ снимается.

Поток:
1. ``collect_xray_user_traffic_all_servers`` обновляет ``user_server_traffic``.
2. ``enforce_traffic_limits_after_collect`` находит превысивших и ставит ``sync_xray_clients_all_servers``.
3. Список клиентов Xray — ``subscription_active_sql()`` (календарь + трафик < лимита или лимит NULL).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from redis.exceptions import RedisError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.domain.subscription.validity import subscription_calendar_active_sql
from app.domain.user_traffic import user_traffic_over_limit_sql
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.traffic_limit")


@dataclass(frozen=True, slots=True)
class TrafficLimitEnforceResult:
    """Итог проверки после батч-сбора трафика."""

    over_limit_count: int = 0
    over_limit_user_ids: tuple[int, ...] = ()
    sync_enqueued: bool = False


def default_traffic_limit_bytes(cfg: Settings | None = None) -> int:
    """Дефолтный лимит из настроек (GiB → байты)."""
    cfg = cfg or settings
    gib = max(1, int(cfg.trial_traffic_limit_gib))
    return gib * 1024 * 1024 * 1024


def apply_default_traffic_limit_for_new_client(user: User, *, cfg: Settings | None = None) -> None:
    """Новый клиент без оплаты: персональный лимит = дефолт из settings."""
    if user.account_role != "client":
        return
    if user.traffic_limit_bytes is not None:
        return
    user.traffic_limit_bytes = default_traffic_limit_bytes(cfg)


def traffic_limit_quota_applies_sql():
    """Клиенты с заданным лимитом и активной календарной подпиской (кандидаты на проверку)."""
    return and_(
        User.account_role == "client",
        User.traffic_limit_bytes.isnot(None),
        subscription_calendar_active_sql(),
    )


def user_traffic_quota_exceeded(user: User, *, used_bytes: int) -> bool:
    """Исчерпан персональный лимит (нужен актуальный ``used_bytes``)."""
    limit = user.traffic_limit_bytes
    if limit is None:
        return False
    used = max(0, int(used_bytes))
    return used >= int(limit)


def enforce_traffic_limits_after_collect(
    session: Session,
    *,
    cfg: Settings | None = None,
) -> TrafficLimitEnforceResult:
    """
    После сбора трафика: найти клиентов с ``used >= traffic_limit_bytes``, поставить sync Xray.

    Строки пользователей не меняются — доступ определяется сравнением трафика с лимитом в SQL/API.
    """
    cfg = cfg or settings
    if not cfg.trial_traffic_limit_enabled:
        return TrafficLimitEnforceResult()

    over_ids = [
        int(uid)
        for uid in session.scalars(
            select(User.id).where(
                traffic_limit_quota_applies_sql(),
                User.id.in_(user_traffic_over_limit_sql()),
            ),
        ).all()
    ]

    sync_enqueued = False
    if over_ids:
        log.info(
            "traffic limit: превысили лимит user_id=%s (всего=%s)",
            over_ids[:50] if len(over_ids) > 50 else over_ids,
            len(over_ids),
        )
        sync_enqueued = enqueue_xray_clients_sync_for_access_change()

    return TrafficLimitEnforceResult(
        over_limit_count=len(over_ids),
        over_limit_user_ids=tuple(over_ids),
        sync_enqueued=sync_enqueued,
    )


def enqueue_xray_clients_sync_for_access_change() -> bool:
    """Один батч sync на все узлы — список клиентов из ``subscription_active_sql()``."""
    from app.domain.users.xray_sync_queue import ensure_sync_xray_clients_all_servers_enqueued

    try:
        job_id = ensure_sync_xray_clients_all_servers_enqueued()
        log.info("traffic limit: в очереди sync Xray клиентов job_id=%s", job_id)
        return True
    except RedisError:
        log.warning(
            "traffic limit: не удалось поставить sync Xray (Redis)",
            exc_info=True,
        )
        return False


async def clear_traffic_limit_after_payment(
    session: AsyncSession,
    user: User,
) -> bool:
    """После оплаты — безлимит (NULL); вызывающий код может поставить sync Xray."""
    if user.traffic_limit_bytes is None:
        return False
    user.traffic_limit_bytes = None
    await session.flush()
    log.info("traffic limit: снят лимит после оплаты user_id=%s", user.id)
    return True
