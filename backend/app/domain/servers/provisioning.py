"""Оркестрация очередей установки ПО и синхронизации Xray-клиентов на узлах.

Сами задачи кладёт в RQ пакет очередей (:mod:`app.domain.servers.provision_queue`,
:mod:`app.domain.users.xray_sync_queue`); здесь — проверки состояния узла перед постановкой
и перевод «зависшего» статуса установки в ``idle``.
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError
from rq.job import Job
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.domain.models.servers import (
    XrayClientsSyncOneResultRead,
    XrayClientsSyncResultRead,
)
from app.domain.servers.provision_queue import (
    enqueue_software_job,
    provision_command_blocks_split_install,
)
from app.domain.users.xray_sync_queue import (
    ensure_sync_xray_clients_all_servers_enqueued,
    ensure_sync_xray_clients_to_server_enqueued,
)
from app.infrastructure.cache import get_redis
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.servers.provisioning")

_XRAY_SYNCABLE_PROXY_KINDS = ("vless", "vless_grpc", "vless_ws", "vless_vk_cdn_xhttp")


def enqueue_sync_xray_all(cfg: Settings | None = None) -> XrayClientsSyncResultRead:
    """Поставить полную синхронизацию Xray-клиентов на всех ``provision_ready`` узлах."""
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    try:
        job_id = ensure_sync_xray_clients_all_servers_enqueued()
    except RedisError as e:
        log.exception("Redis/RQ недоступен (sync Xray)")
        raise ServiceUnavailableError(f"Очередь недоступна: {e}") from e
    return XrayClientsSyncResultRead(job_id=job_id)


async def enqueue_sync_xray_one(
    session: AsyncSession,
    server_id: int,
    cfg: Settings | None = None,
) -> XrayClientsSyncOneResultRead:
    """Поставить точечную синхронизацию Xray-клиентов на одном узле."""
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    if not server.provision_ready:
        raise ConflictError(
            "Узел не готов (provision_ready=false); сначала установите ПО",
        )
    if (server.proxy_kind or "vless").strip().lower() not in _XRAY_SYNCABLE_PROXY_KINDS:
        raise ConflictError("Синхронизация Xray-клиентов доступна только для VLESS-узлов")
    try:
        job_id = ensure_sync_xray_clients_to_server_enqueued(server_id)
    except RedisError as e:
        log.exception("Redis/RQ недоступен (sync Xray)")
        raise ServiceUnavailableError(f"Очередь недоступна: {e}") from e
    return XrayClientsSyncOneResultRead(server_id=server_id, job_id=job_id)


async def enqueue_full_provision(
    session: AsyncSession, server_id: int, cfg: Settings | None = None,
) -> Server:
    """Полная установка ПО узла с нуля (помечает его не готовым на время прогона)."""
    cfg = cfg or settings
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise ConflictError("Установка уже в очереди или выполняется")
    if server.provision_status == "success" and server.provision_ready:
        raise ConflictError(
            "Узел уже помечен как готовый; сбросьте статус в БД для повторной установки",
        )
    return await enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=False,
        clear_ready=True,
        cfg=cfg,
    )


async def reset_server_provision(session: AsyncSession, server_id: int) -> Server:
    """Сбросить «зависший» статус установки и попытаться отменить задачу в RQ.

    Используется когда задача установки висит ``queued/running`` дольше разумного: после
    сброса можно поставить новую задачу. Падение отмены RQ — не блокер, статус всё равно
    переключается в ``idle``.
    """
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    if server.provision_status not in ("queued", "running"):
        raise ConflictError("Сброс только для статусов «в очереди» или «установка»")
    jid = (server.provision_job_id or "").strip()
    if jid:
        try:
            job = Job.fetch(jid, connection=get_redis())
            job.cancel()
        except Exception as e:
            log.warning("Не удалось отменить задачу RQ %s: %s", jid, e)
    server.provision_status = "idle"
    server.provision_job_id = None
    server.provision_error = "Статус сброшен вручную; можно снова поставить задачу в очередь"
    await session.flush()
    return server


async def enqueue_server_reconcile(
    session: AsyncSession, server_id: int, cfg: Settings | None = None,
) -> Server:
    """Прогнать reconcile (проверка/выравнивание) ПО узла без снятия флага ``provision_ready``."""
    cfg = cfg or settings
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise ConflictError("Уже выполняется установка или синхронизация")
    return await enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=True,
        clear_ready=False,
        cfg=cfg,
    )


async def enqueue_component_install(
    session: AsyncSession,
    server_id: int,
    *,
    component: str,
    cfg: Settings | None = None,
) -> Server:
    """Установка/обновление одного компонента (например ``xray`` или ``nginx``)."""
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise ConflictError("Уже в очереди или выполняется")
    return await enqueue_software_job(session, server, component=component, cfg=cfg)
