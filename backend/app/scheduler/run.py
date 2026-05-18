"""Отдельный процесс с периодическими корутинами (Prometheus-load, Xray-сбор, daily Xray sync,
TCP-доступность узлов в Redis, задачи Telegram ``notify_sub_expire_*``).

До рефакторинга часть этих задач жила в ``lifespan`` API. Они работают через
``run_in_threadpool`` поверх sync ``SessionLocal`` / sync httpx, и при горизонтальном
масштабировании API дублировали бы работу. Здесь один или два процесса на весь стек
(см. ``SCHEDULER_ROLE``).

Запускается как ``python -m app.scheduler.run`` (см. ``scheduler-periodic`` и
``scheduler-telegram-notify`` в ``deploy/docker-compose.yml``).

Что куда отнесено:

* **periodic** — сбор трафика Xray, ежедневный sync клиентов Xray (RQ), sync нагрузки из Prometheus,
  фоновый TCP-опрос узлов.
* **telegram_notify** — раз в сутки ``notify_sub_expire_*``; периодически (~5 мин)
  ``notify_reg_1h_has_traffic`` / ``notify_reg_1h_no_traffic`` после регистрации.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Awaitable, Callable

from app.config import settings
from app.core.logging_config import setup_logging

log = logging.getLogger("app.scheduler")


async def _run_until_stopped(
    factories: list[Callable[[], Awaitable[None]]],
) -> None:
    """Поднять все включённые корутины и ждать SIGTERM/SIGINT (graceful)."""
    if not factories:
        log.warning(
            "scheduler: ни одна периодическая задача не включена для role=%s; "
            "процесс закончится сразу. Проверьте SCHEDULER_ROLE и флаги *_SCHEDULE_ENABLED / "
            "subscription_expiry_notify_schedule_enabled.",
            settings.scheduler_role,
        )
        return

    tasks = [asyncio.create_task(coro_factory()) for coro_factory in factories]
    stop_event = asyncio.Event()

    def _request_stop(*_: object) -> None:
        log.info("scheduler: получен сигнал остановки")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: signal.signal только в основном потоке, а add_signal_handler
            # не работает. Запуск там не предполагается (контейнер на linux).
            signal.signal(sig, _request_stop)

    stop_waiter = asyncio.create_task(stop_event.wait())
    done, _pending = await asyncio.wait(
        [*tasks, stop_waiter],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for d in done:
        if d is stop_waiter:
            continue
        # Если корутина упала с исключением — выводим её в лог. Сами не падаем,
        # docker сам поднимет нас при выходе с ненулевым кодом ниже.
        exc = d.exception()
        if exc is not None:
            log.exception("scheduler: задача упала с ошибкой", exc_info=exc)

    for t in tasks:
        if not t.done():
            t.cancel()
    for t in tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("scheduler: ошибка при завершении задачи")


async def main() -> None:
    setup_logging(settings.log_level)
    role = settings.scheduler_role
    log.info("scheduler: запуск (process for periodic background loops, role=%s)", role)

    # Гарантируем, что схема существует — на чистом окружении API мог ещё не успеть
    # её создать. Идемпотентно.
    from app.infrastructure.database.schema import ensure_schema

    ensure_schema()

    include_periodic = role in ("all", "periodic")
    include_telegram_notify = role in ("all", "telegram_notify")

    factories: list[Callable[[], Awaitable[None]]] = []

    if include_periodic and settings.xray_traffic_collect_schedule_enabled:
        from app.infrastructure.xray.xray_traffic_scheduler import (
            periodic_xray_traffic_collect_loop,
        )

        factories.append(periodic_xray_traffic_collect_loop)
        log.info("scheduler: включён сбор трафика Xray (xray_traffic_collect_schedule)")
    elif include_periodic:
        log.info("scheduler: сбор трафика Xray выключен")

    if include_periodic and settings.subscription_daily_xray_clients_sync_enabled:
        from app.domain.subscription.scheduler import subscription_daily_xray_sync_loop

        factories.append(subscription_daily_xray_sync_loop)
        log.info("scheduler: включён ежедневный sync клиентов Xray")
    elif include_periodic:
        log.info("scheduler: ежедневный sync клиентов Xray выключен")

    if (
        include_periodic
        and settings.server_load_prometheus_sync_schedule_enabled
        and (settings.prometheus_base_url or "").strip()
    ):
        from app.infrastructure.prometheus.server_load_scheduler import (
            periodic_server_load_from_prometheus_loop,
        )

        factories.append(periodic_server_load_from_prometheus_loop)
        log.info("scheduler: включён sync servers.load_percent из Prometheus")
    elif include_periodic:
        log.info("scheduler: server load из Prometheus выключен (или нет PROMETHEUS_BASE_URL)")

    if include_periodic and settings.server_reachability_schedule_enabled:
        from app.infrastructure.server_reachability_scheduler import (
            periodic_server_reachability_loop,
        )

        factories.append(periodic_server_reachability_loop)
        log.info("scheduler: включён фоновый TCP-опрос узлов и история в Redis")
    elif include_periodic:
        log.info("scheduler: фоновый опрос доступности узлов выключен")

    if include_telegram_notify and settings.subscription_expiry_notify_schedule_enabled:
        from app.domain.subscription.expiry_notify_scheduler import (
            subscription_expiry_notify_loop,
        )

        factories.append(subscription_expiry_notify_loop)
        log.info(
            "scheduler: включены задачи напоминания об окончании подписки (notify_sub_expire_*)",
        )
    elif include_telegram_notify:
        log.info("scheduler: напоминания об окончании подписки выключены (subscription_expiry_notify)")

    if include_telegram_notify and settings.post_registration_notify_schedule_enabled:
        from app.domain.users.post_registration_notify_scheduler import (
            post_registration_notify_loop,
        )

        factories.append(post_registration_notify_loop)
        log.info(
            "scheduler: включены задачи post-reg (notify_reg_1h_has_traffic / notify_reg_1h_no_traffic)",
        )
    elif include_telegram_notify:
        log.info("scheduler: post-reg уведомления выключены (post_registration_notify)")

    await _run_until_stopped(factories)


if __name__ == "__main__":
    asyncio.run(main())
