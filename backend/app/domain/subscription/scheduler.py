"""Планировщик ежедневной синхронизации списка клиентов Xray на узлах.

Перед постановкой RQ sync создаются задачи ``notify_sub_expire`` (подписка уже истекла по UTC,
см. ``enqueue_subscription_expired_notification_tasks``). Запускается из процесса
``python -m app.scheduler.run`` (роль ``periodic`` / ``all``).
"""

from __future__ import annotations

import asyncio
import logging

from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.time import seconds_until_next_local_time
from app.domain.subscription.expiry_notify_jobs import (
    enqueue_subscription_expired_7d_notification_tasks,
    enqueue_subscription_expired_notification_tasks,
)
from app.domain.users.xray_sync_queue import ensure_sync_xray_clients_all_servers_enqueued

log = logging.getLogger("app.subscription.scheduler")


def run_daily_xray_clients_sync_enqueue() -> None:
    """Поставить в очередь sync inbound (идемпотентно, см. coalesce по job_id в users_service).

    Перед постановкой sync создаёт задачи ``notify_sub_expire`` в ``tasks`` для пользователей,
    у которых по UTC истёк срок (первый день без доступа — см. ``enqueue_subscription_expired_notification_tasks``).
    """
    try:
        n_expire = enqueue_subscription_expired_notification_tasks()
        n_expire_7d = enqueue_subscription_expired_7d_notification_tasks()
        if n_expire or n_expire_7d:
            log.info(
                "Ежедневный sync Xray: notify_sub_expire=%s, notify_sub_expired_7d=%s",
                n_expire,
                n_expire_7d,
            )
    except Exception:
        log.exception(
            "Ежедневный sync Xray: ошибка при создании notify_sub_expire / notify_sub_expired_7d",
        )
    try:
        jid = ensure_sync_xray_clients_all_servers_enqueued()
        log.info("Ежедневный sync клиентов Xray на всех серверах: job_id=%s", jid)
    except RedisError:
        log.warning(
            "Ежедневный sync клиентов Xray: не удалось поставить в очередь (Redis)",
            exc_info=True,
        )


async def subscription_daily_xray_sync_loop() -> None:
    """Корутина lifespan API: раз в сутки в заданное локальное время."""
    if not settings.subscription_daily_xray_clients_sync_enabled:
        log.info("Планировщик ежедневного sync Xray выключен")
        return
    hour = int(settings.subscription_daily_xray_clients_sync_hour_local)
    minute = int(settings.subscription_daily_xray_clients_sync_minute_local)
    log.info(
        "Планировщик ежедневного sync Xray: локальное время %02d:%02d",
        hour,
        minute,
    )
    try:
        while True:
            delay = seconds_until_next_local_time(hour, minute)
            log.debug(
                "Ежедневный sync Xray: сон %.0f с до следующего запуска",
                delay,
            )
            await asyncio.sleep(delay)
            try:
                await run_in_threadpool(run_daily_xray_clients_sync_enqueue)
            except Exception:
                log.exception("Ежедневный sync Xray: ошибка")
    except asyncio.CancelledError:
        log.info("Планировщик ежедневного sync Xray остановлен")
        raise
