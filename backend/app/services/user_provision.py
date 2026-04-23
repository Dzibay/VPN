"""Генерация идентификаторов пользователя VPN и постановка синхронизации Xray в очередь."""

from __future__ import annotations

import logging
import uuid as uuid_lib
from secrets import token_urlsafe

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.queue import get_install_queue

log = logging.getLogger("app.user_provision")

_SUBSCRIPTION_TOKEN_BYTES = 24


def new_subscription_token() -> str:
    return token_urlsafe(_SUBSCRIPTION_TOKEN_BYTES)


def new_vless_uuid() -> str:
    return str(uuid_lib.uuid4())


def enqueue_sync_xray_clients_all_servers() -> None:
    try:
        q = get_install_queue()
        q.enqueue(
            "worker.jobs.sync_xray_clients_all_servers",
            job_timeout=max(settings.provision_job_timeout, 600),
        )
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь синхронизацию Xray (Redis недоступен)",
            exc_info=True,
        )
