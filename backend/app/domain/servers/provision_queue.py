"""Постановка задач установки/обслуживания серверного ПО в очередь RQ.

В отличие от sync-Xray-очереди здесь идемпотентность поверх стабильного ``job_id`` не
используется: задачи установки запускаются вручную из админки и не должны самосовпадать
по времени.
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError
from app.infrastructure.cache import get_install_queue
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.servers.provision_queue")


def provision_command_blocks_split_install(cfg: Settings) -> None:
    """Не пускать пошаговую установку, если воркер настроен на внешний ``provision_command``.

    Внешняя команда — это «всё в одном»; смешивать её с шаговыми компонентами (xray, certs,
    nginx по отдельности) нельзя — состояние конфига рискует разъехаться.
    """
    if (cfg.provision_command or "").strip():
        raise BadRequestError(
            "Отключите provision_command на воркере для пошаговой установки и очистки по SSH.",
        )


async def enqueue_software_job(
    session: AsyncSession,
    server: Server,
    *,
    component: str,
    reconcile: bool = False,
    clear_ready: bool = False,
    cfg: Settings | None = None,
) -> Server:
    """Поставить задачу установки/обслуживания ``component`` для конкретного сервера.

    ``reconcile=True`` — выравнивание состояния ПО без снятия флага ``provision_ready``;
    ``clear_ready=True`` — для полной переустановки: на время прогона помечаем узел не готовым.
    """
    cfg = cfg or settings
    try:
        q = get_install_queue()
        job = q.enqueue(
            "app.worker.jobs.install_server_software",
            server.id,
            reconcile=reconcile,
            component=component,
            job_timeout=cfg.provision_job_timeout,
        )
    except RedisError as e:
        log.exception("Redis/RQ недоступен")
        raise ServiceUnavailableError(f"Очередь установки недоступна: {e}") from e

    server.provision_status = "queued"
    server.provision_error = None
    if clear_ready:
        server.provision_ready = False
    server.provision_job_id = job.id
    await session.flush()
    return server
