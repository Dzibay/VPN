"""Ежедневный цикл постановки задач напоминания об окончании подписки (таблица ``tasks``).

``notify_sub_expire_3d`` / ``_1d`` / ``_0d`` и ``notify_sub_expired_7d`` — здесь (12:00 МСК).
``notify_sub_expire`` — в ``subscription_daily_xray_sync_loop`` (00:05 МСК, вместе с sync Xray).
"""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.time import seconds_until_next_moscow_time
from app.domain.subscription.expiry_notify_jobs import (
    enqueue_subscription_expired_7d_notification_tasks,
    enqueue_subscription_expiry_notification_tasks,
)

log = logging.getLogger("app.subscription.expiry_notify_scheduler")


def _run_subscription_expiry_notify_tick() -> None:
    """Напоминания до/после окончания подписки (кроме ``notify_sub_expire`` — см. Xray sync в полночь)."""

    enqueue_subscription_expiry_notification_tasks()
    enqueue_subscription_expired_7d_notification_tasks()


async def subscription_expiry_notify_loop() -> None:
    if not settings.subscription_expiry_notify_schedule_enabled:
        log.info("Планировщик напоминаний об окончании подписки выключен")
        return
    hour = int(settings.subscription_expiry_notify_hour_local)
    minute = int(settings.subscription_expiry_notify_minute_local)
    log.info(
        "Планировщик notify_sub_expire_*: %02d:%02d Europe/Moscow (без тика при старте контейнера)",
        hour,
        minute,
    )
    try:
        while True:
            delay = seconds_until_next_moscow_time(hour, minute)
            log.debug("notify_sub_expire_*: сон %.0f с до следующего запуска", delay)
            await asyncio.sleep(delay)
            try:
                await run_in_threadpool(_run_subscription_expiry_notify_tick)
            except Exception:
                log.exception("notify_sub_expire_*: ошибка при создании задач")
    except asyncio.CancelledError:
        log.info("Планировщик notify_sub_expire_* остановлен")
        raise
