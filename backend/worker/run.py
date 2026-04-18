"""
Запуск воркера RQ (из каталога backend):

    python -m worker.run

Требуется доступ к Redis и PostgreSQL (те же переменные окружения / .env, что у API).
"""

from __future__ import annotations

import logging
import os
import sys

from redis import Redis
from rq import Worker
from rq.worker import SimpleWorker

from app.core.config import settings
from app.core.logging_config import setup_logging


def main() -> None:
    setup_logging(settings.log_level)
    log = logging.getLogger("worker")
    listen = [settings.redis_install_queue_name]
    redis_conn = Redis.from_url(settings.redis_url)
    log.info("Воркер RQ, очередь %s, Redis %s", listen[0], settings.redis_url)
    # Стандартный Worker вызывает os.fork(); на Windows fork нет — нужен SimpleWorker.
    worker_cls = SimpleWorker if not hasattr(os, "fork") else Worker
    log.info("Класс воркера RQ: %s", worker_cls.__name__)
    worker = worker_cls(listen, connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
