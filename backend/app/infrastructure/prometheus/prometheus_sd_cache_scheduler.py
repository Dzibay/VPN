"""Периодическое обновление кэша HTTP SD для Prometheus (без нагрузки на API workers)."""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.domain.services.prometheus_sd_cache import refresh_node_exporter_targets_cache_sync

log = logging.getLogger("app.prometheus_sd_cache_scheduler")


async def periodic_prometheus_sd_cache_loop() -> None:
    interval = max(30, int(settings.prometheus_sd_cache_refresh_interval_seconds))
    initial = max(0, int(settings.prometheus_sd_cache_initial_delay_seconds))
    if initial:
        await asyncio.sleep(initial)

    while True:
        try:
            count = await run_in_threadpool(refresh_node_exporter_targets_cache_sync)
            log.debug("prometheus sd cache: обновлено targets=%s", count)
        except Exception:
            log.exception("prometheus sd cache: ошибка refresh")
        await asyncio.sleep(interval)
