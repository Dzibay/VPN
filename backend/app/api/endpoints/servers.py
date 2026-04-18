import logging
import secrets
import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from rq.job import Job
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import SessionDep, require_admin
from app.core.config import settings
from app.core.queue import get_install_queue, get_redis
from app.database.operations import table_insert
from app.database.session import SessionLocal
from app.models.server import Server
from app.schemas.servers import (
    ServerCreate,
    ServerLoadSyncItemRead,
    ServerLoadSyncResultRead,
    ServerRead,
    ServerUpdate,
    ServersCountResponse,
)
from app.services.server_load_sync import sync_all_servers_load_from_prometheus

log = logging.getLogger("app.servers")

router = APIRouter(
    prefix="/servers",
    tags=["servers"],
    dependencies=[Depends(require_admin)],
)


def _provision_command_blocks_split_install() -> None:
    if (settings.provision_command or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Отключите provision_command на воркере для пошаговой установки и очистки по SSH.",
        )


def _enqueue_software_job(
    session: Session,
    server: Server,
    *,
    component: str,
    reconcile: bool = False,
    clear_ready: bool = False,
) -> Server:
    try:
        q = get_install_queue()
        job = q.enqueue(
            "worker.jobs.install_server_software",
            server.id,
            reconcile=reconcile,
            component=component,
            job_timeout=settings.provision_job_timeout,
        )
    except RedisError as e:
        log.exception("Redis/RQ недоступен")
        raise HTTPException(
            status_code=503,
            detail=f"Очередь установки недоступна: {e}",
        ) from e

    server.provision_status = "queued"
    server.provision_error = None
    if clear_ready:
        server.provision_ready = False
    server.provision_job_id = job.id
    session.flush()
    return server


@router.get(
    "/count",
    response_model=ServersCountResponse,
    summary="Количество серверов в БД",
)
async def servers_count(session: SessionDep) -> ServersCountResponse:
    total = session.scalar(select(func.count()).select_from(Server))
    return ServersCountResponse(servers_count=int(total or 0))


@router.get(
    "",
    response_model=list[ServerRead],
    summary="Список серверов",
)
async def list_servers(session: SessionDep) -> list[Server]:
    stmt = select(Server).order_by(Server.id.desc())
    return list(session.scalars(stmt).all())


@router.post(
    "/sync-load-from-prometheus",
    response_model=ServerLoadSyncResultRead,
    summary=(
        "Записать в БД load_percent по Prometheus: среднее «узкое место» за окно "
        "(как на графике аналитики)"
    ),
)
async def sync_load_from_prometheus(
    hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Окно в часах для усреднения (по умолчанию сутки)",
    ),
) -> ServerLoadSyncResultRead:
    def _run() -> ServerLoadSyncResultRead:
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

    return await run_in_threadpool(_run)
@router.post(
    "",
    response_model=ServerRead,
    status_code=201,
    summary="Добавить сервер",
)
async def create_server(body: ServerCreate, session: SessionDep) -> Server:
    vless_uuid = body.vless_uuid or str(uuid_lib.uuid4())
    reality_short_id = body.reality_short_id or secrets.token_hex(4)
    reality_dest = body.reality_dest or "www.amazon.com:443"
    reality_server_names = body.reality_server_names or "www.amazon.com,amazon.com"
    reality_fingerprint = body.reality_fingerprint or "chrome"
    vless_flow = body.vless_flow or "xtls-rprx-vision"
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
    )
    try:
        table_insert(session, server)
    except IntegrityError as e:
        log.warning("create_server conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Сервер с таким host и port уже существует",
        ) from e
    return server


@router.post(
    "/{server_id}/provision",
    response_model=ServerRead,
    status_code=202,
    summary="Поставить в очередь установку ПО на узел (воркер RQ)",
)
async def enqueue_server_provision(
    server_id: int,
    session: SessionDep,
) -> Server:
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Установка уже в очереди или выполняется",
        )
    if server.provision_status == "success" and server.provision_ready:
        raise HTTPException(
            status_code=409,
            detail="Узел уже помечен как готовый; сбросьте статус в БД для повторной установки",
        )
    return _enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=False,
        clear_ready=True,
    )


@router.post(
    "/{server_id}/provision/reset",
    response_model=ServerRead,
    status_code=200,
    summary="Сбросить застрявший статус очереди (queued/running) и отменить задачу RQ",
)
async def reset_server_provision(
    server_id: int,
    session: SessionDep,
) -> Server:
    """
    Если воркер упал, в БД может остаться queued/running — повторно поставить в очередь нельзя.
    Сброс переводит узел в idle и пытается отменить последнюю задачу в Redis.
    """
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status not in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Сброс только для статусов «в очереди» или «установка»",
        )
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


@router.post(
    "/{server_id}/provision/reconcile",
    response_model=ServerRead,
    status_code=202,
    summary="Проверить узел и донастроить ПО (xray, node_exporter) — повторный прогон скрипта",
)
async def enqueue_server_reconcile(
    server_id: int,
    session: SessionDep,
) -> Server:
    """
    Доступно, пока нет активной задачи (queued/running).
    Не сбрасывает «готовность» заранее: во время выполнения статус running, по успеху снова success.
    """
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Уже выполняется установка или синхронизация",
        )
    return _enqueue_software_job(
        session,
        server,
        component="all",
        reconcile=True,
        clear_ready=False,
    )


@router.post(
    "/{server_id}/provision/xray",
    response_model=ServerRead,
    status_code=202,
    summary="Только Xray (VLESS+REALITY) на узле",
)
async def enqueue_server_provision_xray(
    server_id: int,
    session: SessionDep,
) -> Server:
    _provision_command_blocks_split_install()
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Уже в очереди или выполняется",
        )
    return _enqueue_software_job(session, server, component="xray")


@router.post(
    "/{server_id}/provision/prometheus",
    response_model=ServerRead,
    status_code=202,
    summary="Только node_exporter (метрики Prometheus) на узле",
)
async def enqueue_server_provision_prometheus(
    server_id: int,
    session: SessionDep,
) -> Server:
    _provision_command_blocks_split_install()
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Уже в очереди или выполняется",
        )
    return _enqueue_software_job(session, server, component="prometheus")


@router.post(
    "/{server_id}/provision/cleanup",
    response_model=ServerRead,
    status_code=202,
    summary="Очистить узел (xray + node_exporter) и сбросить ключи/метрики в БД",
)
async def enqueue_server_provision_cleanup(
    server_id: int,
    session: SessionDep,
) -> Server:
    _provision_command_blocks_split_install()
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if server.provision_status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Уже в очереди или выполняется",
        )
    return _enqueue_software_job(session, server, component="cleanup")


@router.patch(
    "/{server_id}",
    response_model=ServerRead,
    summary="Обновить сервер (нагрузка, страна, имя, активность)",
)
async def patch_server(
    server_id: int,
    body: ServerUpdate,
    session: SessionDep,
) -> Server:
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return server
    if data.get("reality_private_key"):
        server.reality_public_key = None
    for key, value in data.items():
        setattr(server, key, value)
    session.flush()
    return server
