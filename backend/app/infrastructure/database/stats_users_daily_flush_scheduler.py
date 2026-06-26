"""Периодический flush очереди stats_users_daily_dirty (умный кэш)."""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.infrastructure.database.stats_mv_refresh import flush_users_daily_stats_dirty_sync

log = logging.getLogger("app.stats_users_daily_flush_scheduler")


async def periodic_stats_users_daily_flush_loop() -> None:
    interval = max(15, int(settings.stats_users_daily_flush_interval_seconds))
    initial = max(0, int(settings.stats_users_daily_flush_initial_delay_seconds))
    log.info(
        "stats users daily flush: запущен (интервал=%ss, задержка=%ss)",
        interval,
        initial,
    )
    try:
        await asyncio.sleep(initial)
        while True:
            try:
                n = await run_in_threadpool(flush_users_daily_stats_dirty_sync)
                if n > 0:
                    log.debug("stats users daily flush: обновлено строк=%s", n)
            except Exception:
                log.exception("stats users daily flush: ошибка тика")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("stats users daily flush: остановлен")
        raise
