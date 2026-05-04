"""Отдельный процесс с периодическими корутинами (Prometheus-load, Xray-сбор, daily sync).

До рефакторинга эти три фоновые задачи жили в ``lifespan`` API. Они работают через
``run_in_threadpool`` поверх sync ``SessionLocal`` / sync httpx, и при горизонтальном
масштабировании API дублировали бы работу. Здесь один процесс на весь стек.

Запускается как ``python -m app.scheduler.run`` (см. сервис ``scheduler`` в
``deploy/docker-compose.yml``).
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
            "scheduler: ни одна периодическая задача не включена в настройках; "
            "процесс закончится сразу. Включите хотя бы одну переменную "
            "*_SCHEDULE_ENABLED, иначе контейнер не нужен.",
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
    log.info("scheduler: запуск (process for periodic background loops)")

    # Гарантируем, что схема существует — на чистом окружении API мог ещё не успеть
    # её создать. Идемпотентно.
    from app.infrastructure.database.schema import ensure_schema

    ensure_schema()

    factories: list[Callable[[], Awaitable[None]]] = []

    if settings.xray_traffic_collect_schedule_enabled:
        from app.infrastructure.xray.xray_traffic_scheduler import (
            periodic_xray_traffic_collect_loop,
        )

        factories.append(periodic_xray_traffic_collect_loop)
        log.info("scheduler: включён сбор трафика Xray (xray_traffic_collect_schedule)")
    else:
        log.info("scheduler: сбор трафика Xray выключен")

    if settings.subscription_daily_xray_clients_sync_enabled:
        from app.domain.subscription.scheduler import subscription_daily_xray_sync_loop

        factories.append(subscription_daily_xray_sync_loop)
        log.info("scheduler: включён ежедневный sync клиентов Xray")
    else:
        log.info("scheduler: ежедневный sync клиентов Xray выключен")

    if settings.server_load_prometheus_sync_schedule_enabled and (
        settings.prometheus_base_url or ""
    ).strip():
        from app.infrastructure.prometheus.server_load_scheduler import (
            periodic_server_load_from_prometheus_loop,
        )

        factories.append(periodic_server_load_from_prometheus_loop)
        log.info("scheduler: включён sync servers.load_percent из Prometheus")
    else:
        log.info("scheduler: server load из Prometheus выключен (или нет PROMETHEUS_BASE_URL)")

    await _run_until_stopped(factories)


if __name__ == "__main__":
    asyncio.run(main())
