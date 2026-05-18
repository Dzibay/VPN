"""Периодический цикл постановки задач ``notify_reg_1h_*`` (~1 ч после регистрации)."""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.domain.users.post_registration_notify_jobs import enqueue_post_registration_notification_tasks

log = logging.getLogger("app.users.post_registration_notify_scheduler")


async def post_registration_notify_loop() -> None:
    if not settings.post_registration_notify_schedule_enabled:
        log.info("Планировщик notify_reg_1h_* выключен")
        return

    interval = max(60, int(settings.post_registration_notify_interval_seconds))
    initial = max(0, int(settings.post_registration_notify_initial_delay_seconds))
    log.info(
        "Планировщик notify_reg_1h_*: интервал=%ss, задержка до 1-го тика=%ss, delay=%sh, lookback=%smin",
        interval,
        initial,
        settings.post_registration_notify_delay_hours,
        settings.post_registration_notify_lookback_minutes,
    )
    try:
        await asyncio.sleep(initial)
        while True:
            try:
                await run_in_threadpool(enqueue_post_registration_notification_tasks)
            except Exception:
                log.exception("notify_reg_1h_*: ошибка при создании задач")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("Планировщик notify_reg_1h_* остановлен")
        raise
