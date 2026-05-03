"""
Запуск воркера RQ (из каталога backend). Задачи очереди описаны в ``app.worker.jobs``.

    python -m worker.run

Требуется доступ к Redis и PostgreSQL (те же переменные окружения / .env, что у API).

Почему кажется, что процесс «завис»:
- В простое воркер ждёт задачи в Redis (блокирующее ожидание) — это нормально.
- На Windows используется SimpleWorker: установка по SSH выполняется в том же процессе.
  Пока идёт ssh (до provision_subprocess_timeout сек.), Ctrl+C может не завершить процесс
  сразу: первое прерывание — мягкая остановка после текущей задачи; второе — принудительный
  выход. Если SSH подвис, завершите воркер через Диспетчер задач или остановите ssh.exe.

Отладка без вечного ожидания очереди:
    set WORKER_BURST=1
    python -m worker.run
    (обработает текущие задачи в очереди и выйдет)

Ctrl+C «не срабатывает» в простое: у RQ по умолчанию worker_ttl=420, очередь опрашивается блокировкой
на (worker_ttl − 15) секунд (~405 с). Пока идёт этот запрос к Redis, Python не обрабатывает SIGINT.
Здесь по умолчанию выставлен более короткий worker_ttl; свой: set WORKER_TTL=420
"""

from __future__ import annotations

import logging
import os
import sys

from redis import Redis
from rq import Worker
from rq.defaults import DEFAULT_WORKER_TTL
from rq.worker import SimpleWorker

from app.config import settings
from app.core.logging_config import setup_logging
from app.infrastructure.database.schema import ensure_schema


def _worker_ttl() -> int:
    """
    Короткий TTL → короткий dequeue-timeout → Ctrl+C обрабатывается в простое без многоминутной паузы.
    Минимум 20 (у RQ dequeue_timeout = max(1, worker_ttl - 15)).
    """
    raw = (os.environ.get("WORKER_TTL") or "").strip()
    if raw:
        return max(20, int(raw))
    return 60


def _redis_connection() -> Redis:
    """
    Явные таймауты: иначе при «мёртвом» Redis клиент может долго висеть на connect/BLPOP.
    """
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=10,
        socket_timeout=120,
        health_check_interval=30,
    )


def main() -> None:
    setup_logging(settings.log_level)
    ensure_schema()
    log = logging.getLogger("worker")
    listen = [settings.redis_install_queue_name]
    redis_conn = _redis_connection()
    log.info("Воркер RQ, очередь %s, Redis %s", listen[0], settings.redis_url)
    # Стандартный Worker вызывает os.fork(); на Windows fork нет — нужен SimpleWorker.
    worker_cls = SimpleWorker if not hasattr(os, "fork") else Worker
    log.info("Класс воркера RQ: %s", worker_cls.__name__)
    if worker_cls is SimpleWorker:
        log.warning(
            "SimpleWorker: задачи (SSH) бегут в этом процессе — длинная установка блокирует "
            "выход по одному Ctrl+C; см. docstring worker/run.py",
        )
    ttl = _worker_ttl()
    dequeue_block = max(1, ttl - 15)
    if ttl != DEFAULT_WORKER_TTL:
        log.info(
            "worker_ttl=%s (блокировка ожидания задачи в Redis до ~%s с; для RQ по умолчанию было бы %s с). "
            "Свой TTL: WORKER_TTL=…",
            ttl,
            dequeue_block,
            max(1, DEFAULT_WORKER_TTL - 15),
        )
    worker = worker_cls(listen, connection=redis_conn, worker_ttl=ttl)
    burst = (os.environ.get("WORKER_BURST") or "").strip() in ("1", "true", "yes")
    if burst:
        log.info("Режим WORKER_BURST: обработать очередь и выйти")
    worker.work(with_scheduler=False, burst=burst)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
