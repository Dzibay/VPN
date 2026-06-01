"""
Планировщик батч-сбора трафика Xray (очередь RQ + Redis lock при периодическом enqueue).

Ручной запуск из API обходит lock — см. enqueue_xray_traffic_collect_batch_admin.
"""

from __future__ import annotations

import asyncio
import logging
import secrets

from redis.exceptions import RedisError

from app.config import settings
from starlette.concurrency import run_in_threadpool

from app.infrastructure.cache import get_install_queue, get_redis

log = logging.getLogger("app.xray_traffic_scheduler")

SCHEDULE_LOCK_KEY = "vpn:xray_traffic:schedule_lock"

# Снять lock только если он всё ещё наш (значение == токен): защищает от снятия
# чужого lock'а (например, после истечения TTL и нового захвата).
_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)


def _schedule_lock_ttl_seconds() -> int:
    """TTL lock'а батча.

    Lock держится всё время выполнения батча и снимается worker'ом по завершении
    (``release_schedule_lock``). TTL — только страховка на случай падения worker, поэтому
    он не меньше таймаута job: иначе при сборе дольше интервала стартовал бы второй батч
    и дублировал записи в ``user_server_traffic``.
    """
    interval = int(settings.xray_traffic_collect_interval_seconds)
    job_timeout = int(settings.xray_traffic_batch_job_timeout_seconds)
    return max(60, interval, job_timeout + 60)


def release_schedule_lock(token: str | None) -> None:
    """Снять расписательный lock, если он всё ещё принадлежит этому батчу."""
    if not token:
        return
    try:
        get_redis().eval(_RELEASE_LOCK_LUA, 1, SCHEDULE_LOCK_KEY, token)
    except RedisError:
        log.warning("xray traffic schedule: не удалось снять lock (истечёт по TTL)")


def try_enqueue_periodic_xray_traffic_batch() -> str | None:
    """
    Один тик планировщика: взять lock в Redis и поставить батч в RQ.

    Lock снимается worker'ом по завершении батча (``release_schedule_lock``), поэтому
    пока батч выполняется, следующий тик его не продублирует.
    Возвращает job_id или None, если lock занят / Redis недоступен.
    """
    token = secrets.token_hex(16)
    try:
        r = get_redis()
        if not r.set(SCHEDULE_LOCK_KEY, token, nx=True, ex=_schedule_lock_ttl_seconds()):
            log.debug("xray traffic schedule: пропуск тика (предыдущий батч ещё выполняется)")
            return None
    except RedisError:
        log.exception("xray traffic schedule: Redis недоступен")
        return None

    try:
        q = get_install_queue()
        job = q.enqueue(
            "app.worker.jobs.collect_xray_user_traffic_all_servers",
            kwargs={"schedule_lock_token": token},
            job_timeout=int(settings.xray_traffic_batch_job_timeout_seconds),
        )
    except Exception:
        log.exception("xray traffic schedule: ошибка постановки в очередь")
        release_schedule_lock(token)
        return None

    log.info("xray traffic schedule: в очереди батч job_id=%s", job.id)
    return job.id


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
