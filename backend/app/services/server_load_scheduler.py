"""
Фоновая синхронизация servers.load_percent из Prometheus (без привязки к запросам /sub).
"""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.database.session import SessionLocal
from app.services.server_load_sync import sync_all_servers_load_from_prometheus

log = logging.getLogger("app.server_load_scheduler")

_SYNC_HOURS = 24


def run_scheduled_server_load_sync() -> None:
    if not (settings.prometheus_base_url or "").strip():
        return
    db = SessionLocal()
    try:
        rep = sync_all_servers_load_from_prometheus(db, hours=_SYNC_HOURS)
        updated = sum(1 for i in rep.items if i.ok)
        failed = len(rep.items) - updated
        log.info(
            "scheduled server load sync: ok=%s failed=%s (hours=%s)",
            updated,
            failed,
            rep.hours,
        )
    except Exception:
        log.exception("scheduled server load sync: ошибка")
    finally:
        db.close()


async def periodic_server_load_from_prometheus_loop() -> None:
    interval = max(60, int(settings.server_load_prometheus_sync_interval_seconds))
    initial = max(0, int(settings.server_load_prometheus_sync_initial_delay_seconds))
    log.info(
        "server load prometheus scheduler: запущен (интервал=%ss, задержка до 1-го тика=%ss)",
        interval,
        initial,
    )
    try:
        await asyncio.sleep(initial)
        while True:
            await run_in_threadpool(run_scheduled_server_load_sync)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("server load prometheus scheduler: остановлен")
        raise
