"""Планировщик ежедневной синхронизации списка клиентов Xray на узлах.

Запускается из lifespan API: раз в сутки ставит в очередь RQ полный sync inbound.
Ставка идемпотентна (см. coalesce по job_id в users_service).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.domain.users.xray_sync_queue import ensure_sync_xray_clients_all_servers_enqueued

log = logging.getLogger("app.subscription.scheduler")


def _seconds_until_next_local_time(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daily_xray_clients_sync_enqueue() -> None:
    """Поставить в очередь sync inbound (идемпотентно, см. coalesce по job_id в users_service)."""
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
            delay = _seconds_until_next_local_time(hour, minute)
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
