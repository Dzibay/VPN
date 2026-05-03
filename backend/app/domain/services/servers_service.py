"""Управление записями серверов, каскад, очередь установки и синхронизация нагрузки."""

from __future__ import annotations

import logging
import secrets
import uuid as uuid_lib

from redis.exceptions import RedisError
from rq.job import Job
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.domain.models.servers import (
    ServerCreate,
    ServerLoadSyncItemRead,
    ServerLoadSyncResultRead,
    ServerUpdate,
    ServersCountResponse,
    XrayClientsSyncOneResultRead,
    XrayClientsSyncResultRead,
)
from app.domain.services.http_errors import HttpServiceError
from app.domain.services.users_service import (
    ensure_sync_xray_clients_all_servers_enqueued,
    ensure_sync_xray_clients_to_server_enqueued,
)
from app.infrastructure.cache import get_install_queue, get_redis
from app.infrastructure.database.operations import table_insert
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.prometheus.server_load_sync import sync_all_servers_load_from_prometheus
from app.infrastructure.server_health_check import run_tcp_probes

log = logging.getLogger("app.servers_service")


def validate_cascade_pair(
    session: Session,
    *,
    self_id: int | None,
    is_ru_entry: bool,
    cascade_next_id: int | None,
) -> None:
    if cascade_next_id is None:
        return
    if not is_ru_entry:
        raise HttpServiceError(
            400,
            "cascade_next_server_id задан: включите is_cascade_ru_entry (вход в каскаде) "
            "или сбросьте внешний id",
        )
    if self_id is not None and cascade_next_id == self_id:
        raise HttpServiceError(
            400,
            "cascade_next_server_id не может совпадать с id этого сервера",
        )
    target = session.get(Server, cascade_next_id)
    if target is None:
        raise HttpServiceError(
            400,
            "cascade_next_server_id: внешний сервер не найден",
        )
    if target.is_cascade_ru_entry:
        raise HttpServiceError(
            400,
            "Каскад: внешний узел — сервер с is_cascade_ru_entry=false; "
            "нельзя направлять на вход (РФ) другой пары",
        )
    if target.cascade_next_server_id is not None:
        raise HttpServiceError(
            400,
            "Каскад: внешний узел не должен иметь собственного cascade_next (один уровень)",
        )


def merge_cascade_fields(
    server: Server,
    data: dict,
) -> tuple[bool, int | None]:
    is_ru = server.is_cascade_ru_entry
    next_id = server.cascade_next_server_id
    if "is_cascade_ru_entry" in data:
        is_ru = bool(data["is_cascade_ru_entry"])
    if "cascade_next_server_id" in data:
        next_id = data["cascade_next_server_id"]
    if is_ru is False:
        next_id = None
    elif next_id is not None:
        is_ru = True
    return is_ru, next_id


def try_enqueue_sync_xray_on_exit_for_cascade(session: Session, *exit_ids: int | None) -> None:
    need = {int(x) for x in exit_ids if x is not None}
    for eid in need:
        ex = session.get(Server, eid)
        if ex is None or not ex.provision_ready:
            log.info(
                "cascade: пропуск sync Xray на exit id=%s (нет или provision_ready=false)",
                eid,
            )
            continue
        if (settings.provision_command or "").strip():
            continue
        try:
            ensure_sync_xray_clients_to_server_enqueued(eid)
        except RedisError as e:
            log.warning("cascade: не поставлена в очередь sync Xray на exit id=%s: %s", eid, e)


def provision_command_blocks_split_install(cfg: Settings) -> None:
    if (cfg.provision_command or "").strip():
        raise HttpServiceError(
            400,
            "Отключите provision_command на воркере для пошаговой установки и очистки по SSH.",
        )


def enqueue_software_job(
    session: Session,
    server: Server,
    *,
    component: str,
    reconcile: bool = False,
    clear_ready: bool = False,
    cfg: Settings | None = None,
) -> Server:
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
        raise HttpServiceError(503, f"Очередь установки недоступна: {e}") from e

    server.provision_status = "queued"
    server.provision_error = None
    if clear_ready:
        server.provision_ready = False
    server.provision_job_id = job.id
    session.flush()
    return server


def servers_count(session: Session) -> ServersCountResponse:
    total = session.scalar(select(func.count()).select_from(Server))
    return ServersCountResponse(servers_count=int(total or 0))


def list_servers(session: Session) -> list[Server]:
    stmt = select(Server).order_by(Server.id.desc())
    return list(session.scalars(stmt).all())


def sync_load_from_prometheus_result(hours: int) -> ServerLoadSyncResultRead:
    db = SessionLocal()
    try:
        rep = sync_all_servers_load_from_prometheus(db, hours=hours)
    finally:
        db.close()
    return ServerLoadSyncResultRead(
        hours=rep.hours,
        items=[
            ServerLoadSyncItemRead(
                server_id=i.server_id,
                host=i.host,
                ok=i.ok,
                load_percent=i.load_percent,
                detail=i.detail,
            )
            for i in rep.items
        ],
        updated=sum(1 for i in rep.items if i.ok),
        failed=sum(1 for i in rep.items if not i.ok),
    )


def create_server(session: Session, body: ServerCreate, cfg: Settings | None = None) -> Server:
    cfg = cfg or settings
    vless_uuid = body.vless_uuid or str(uuid_lib.uuid4())
    reality_short_id = body.reality_short_id or secrets.token_hex(4)
    reality_dest = body.reality_dest or "www.amazon.com:443"
    reality_server_names = body.reality_server_names or "www.amazon.com,amazon.com"
    reality_fingerprint = body.reality_fingerprint or "chrome"
    vless_flow = body.vless_flow or "xtls-rprx-vision"
    is_ru = bool(body.is_cascade_ru_entry)
    cnext = body.cascade_next_server_id
    if cnext is not None:
        is_ru = True
    elif not is_ru:
        cnext = None
    validate_cascade_pair(session, self_id=None, is_ru_entry=is_ru, cascade_next_id=cnext)
    cascade_egress_uuid: str | None = str(uuid_lib.uuid4()) if cnext else None
    server = Server(
        name=body.name,
        host=body.host,
        port=body.port,
        country=body.country,
        load_percent=body.load_percent,
        is_active=body.is_active,
        vless_uuid=vless_uuid,
        reality_short_id=reality_short_id,
        reality_dest=reality_dest,
        reality_server_names=reality_server_names,
        reality_fingerprint=reality_fingerprint,
        vless_flow=vless_flow,
        prometheus_instance=body.prometheus_instance,
        network_cap_mbps=body.network_cap_mbps,
        is_cascade_ru_entry=is_ru,
        cascade_next_server_id=cnext,
        cascade_egress_client_uuid=cascade_egress_uuid,
    )
    try:
        table_insert(session, server)
    except IntegrityError as e:
        log.warning("create_server conflict: %s", e)
        raise HttpServiceError(
            409,
            "Сервер с таким host и port уже существует",
        ) from e
    try_enqueue_sync_xray_on_exit_for_cascade(session, cnext)
    return server


def enqueue_sync_xray_all(cfg: Settings | None = None) -> XrayClientsSyncResultRead:
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    try:
        job_id = ensure_sync_xray_clients_all_servers_enqueued()
    except RedisError as e:
        log.exception("Redis/RQ недоступен (sync Xray)")
        raise HttpServiceError(503, f"Очередь недоступна: {e}") from e
    return XrayClientsSyncResultRead(job_id=job_id)


def enqueue_sync_xray_one(
    session: Session,
    server_id: int,
    cfg: Settings | None = None,
) -> XrayClientsSyncOneResultRead:
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    if not server.provision_ready:
        raise HttpServiceError(
            409,
            "Узел не готов (provision_ready=false); сначала установите ПО",
        )
    try:
        job_id = ensure_sync_xray_clients_to_server_enqueued(server_id)
    except RedisError as e:
        log.exception("Redis/RQ недоступен (sync Xray)")
        raise HttpServiceError(503, f"Очередь недоступна: {e}") from e
    return XrayClientsSyncOneResultRead(server_id=server_id, job_id=job_id)


def enqueue_full_provision(session: Session, server_id: int, cfg: Settings | None = None) -> Server:
    cfg = cfg or settings
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HttpServiceError(409, "Установка уже в очереди или выполняется")
    if server.provision_status == "success" and server.provision_ready:
        raise HttpServiceError(
            409,
            "Узел уже помечен как готовый; сбросьте статус в БД для повторной установки",
        )
    return enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=False,
        clear_ready=True,
        cfg=cfg,
    )


def reset_server_provision(session: Session, server_id: int) -> Server:
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    if server.provision_status not in ("queued", "running"):
        raise HttpServiceError(409, "Сброс только для статусов «в очереди» или «установка»")
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
    session.flush()
    return server


def enqueue_server_reconcile(session: Session, server_id: int, cfg: Settings | None = None) -> Server:
    cfg = cfg or settings
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HttpServiceError(409, "Уже выполняется установка или синхронизация")
    return enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=True,
        clear_ready=False,
        cfg=cfg,
    )


def enqueue_component_install(
    session: Session,
    server_id: int,
    *,
    component: str,
    cfg: Settings | None = None,
) -> Server:
    cfg = cfg or settings
    provision_command_blocks_split_install(cfg)
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HttpServiceError(409, "Уже в очереди или выполняется")
    return enqueue_software_job(session, server, component=component, cfg=cfg)


def patch_server(session: Session, server_id: int, body: ServerUpdate) -> Server:
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return server
    priv_in = data.get("reality_private_key")
    if priv_in:
        new_priv = str(priv_in).strip()
        old_priv = (server.reality_private_key or "").strip()
        if new_priv != old_priv:
            server.reality_public_key = None
    cascade_touched = False
    old_cnext: int | None = None
    if "is_cascade_ru_entry" in data or "cascade_next_server_id" in data:
        cascade_touched = True
        old_cnext = server.cascade_next_server_id
        old_cuuid = server.cascade_egress_client_uuid
        is_ru, cnext = merge_cascade_fields(server, data)
        validate_cascade_pair(
            session,
            self_id=server_id,
            is_ru_entry=is_ru,
            cascade_next_id=cnext,
        )
        data["is_cascade_ru_entry"] = is_ru
        data["cascade_next_server_id"] = cnext
        if cnext is None:
            data["cascade_egress_client_uuid"] = None
        elif cnext != old_cnext or not (str(old_cuuid or "").strip()):
            data["cascade_egress_client_uuid"] = str(uuid_lib.uuid4())
    for key, value in data.items():
        setattr(server, key, value)
    session.flush()
    if cascade_touched:
        try_enqueue_sync_xray_on_exit_for_cascade(
            session,
            old_cnext,
            server.cascade_next_server_id,
        )
    return server


def tcp_probes_payload(
    *,
    host: str,
    port: int,
    exit_host: str | None,
    exit_port: int | None,
    timeout_sec: float,
    cfg: Settings | None = None,
) -> dict:
    """Только сетевые пробы; без обращения к БД (можно вызывать из ``run_in_threadpool``)."""
    cfg = cfg or settings
    return run_tcp_probes(
        host,
        port,
        ne_port=int(cfg.provision_node_exporter_port),
        exit_host=exit_host,
        exit_port=exit_port,
        timeout_sec=timeout_sec,
    )


def delete_server(session: Session, server_id: int) -> None:
    server = session.get(Server, server_id)
    if server is None:
        raise HttpServiceError(404, "Сервер не найден")
    session.delete(server)
    session.flush()
