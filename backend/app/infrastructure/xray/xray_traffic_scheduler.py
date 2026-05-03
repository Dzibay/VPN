"""
Планировщик батч-сбора трафика Xray (очередь RQ + Redis lock при периодическом enqueue).

Ручной запуск из API обходит lock — см. enqueue_xray_traffic_collect_batch_admin.
"""

from __future__ import annotations

import asyncio
import logging

from redis.exceptions import RedisError

from app.config import settings
from starlette.concurrency import run_in_threadpool

from app.infrastructure.cache import get_install_queue, get_redis

log = logging.getLogger("app.xray_traffic_scheduler")

SCHEDULE_LOCK_KEY = "vpn:xray_traffic:schedule_lock"


def _schedule_lock_ttl_seconds() -> int:
    return max(30, int(settings.xray_traffic_collect_interval_seconds) - 5)


def try_enqueue_periodic_xray_traffic_batch() -> str | None:
    """
    Один тик планировщика: взять lock в Redis и поставить батч в RQ.
    Возвращает job_id или None, если lock занят / Redis недоступен.
    """
    try:
        r = get_redis()
        if not r.set(SCHEDULE_LOCK_KEY, "1", nx=True, ex=_schedule_lock_ttl_seconds()):
            log.debug("xray traffic schedule: пропуск тика (lock или недавний запуск)")
            return None
        q = get_install_queue()
        job = q.enqueue(
            "app.worker.jobs.collect_xray_user_traffic_all_servers",
            job_timeout=int(settings.xray_traffic_batch_job_timeout_seconds),
        )
        log.info("xray traffic schedule: в очереди батч job_id=%s", job.id)
        return job.id
    except RedisError:
        log.exception("xray traffic schedule: Redis/RQ недоступен")
        try:
            get_redis().delete(SCHEDULE_LOCK_KEY)
        except RedisError:
            pass
        return None
    except Exception:
        log.exception("xray traffic schedule: ошибка постановки в очередь")
        try:
            get_redis().delete(SCHEDULE_LOCK_KEY)
        except RedisError:
            pass
        return None


def enqueue_xray_traffic_collect_batch_admin() -> str:
    """Админский запуск: всегда ставит батч в очередь (без расписательного lock)."""
    q = get_install_queue()
    job = q.enqueue(
        "app.worker.jobs.collect_xray_user_traffic_all_servers",
        job_timeout=int(settings.xray_traffic_batch_job_timeout_seconds),
    )
    log.info("xray traffic collect-all: в очереди батч job_id=%s (ручной)", job.id)
    return job.id


async def periodic_xray_traffic_collect_loop() -> None:
    """Корутина для lifespan API: интервально ставит батч в RQ (с Redis lock)."""
    interval = max(60, int(settings.xray_traffic_collect_interval_seconds))
    initial = max(0, int(settings.xray_traffic_collect_initial_delay_seconds))
    log.info(
        "xray traffic scheduler: запущен (интервал=%ss, задержка до 1-го тика=%ss)",
        interval,
        initial,
    )
    try:
        await asyncio.sleep(initial)
        while True:
            await run_in_threadpool(try_enqueue_periodic_xray_traffic_batch)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("xray traffic scheduler: остановлен")
        raise
