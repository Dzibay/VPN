from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, SessionDep, require_admin
from app.domain.models.servers import (
    ServerCreate,
    ServerLoadSyncResultRead,
    ServerPingRead,
    ServerRead,
    ServerUpdate,
    ServersCountResponse,
    XrayClientsSyncOneResultRead,
    XrayClientsSyncResultRead,
)
from app.domain.services.servers_service import (
    create_server,
    delete_server,
    enqueue_component_install,
    enqueue_full_provision,
    enqueue_server_reconcile,
    enqueue_sync_xray_all,
    enqueue_sync_xray_one,
    list_servers,
    patch_server,
    reset_server_provision,
    servers_count,
    sync_load_from_prometheus_result,
    tcp_probes_payload,
)
from app.domain.users.xray_sync_queue import enqueue_sync_xray_clients_all_servers
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.server_health_check import build_server_health_read

router = APIRouter(
    prefix="/servers",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/count",
    response_model=ServersCountResponse,
    summary="Число записей серверов в базе данных",
)
async def servers_count_ep(session: ReadonlySessionDep) -> ServersCountResponse:
    return servers_count(session)


@router.get(
    "",
    response_model=list[ServerRead],
    summary="Перечень серверов",
)
async def list_servers_ep(session: ReadonlySessionDep) -> list[Server]:
    return list_servers(session)


@router.post(
    "/sync-load-from-prometheus",
    response_model=ServerLoadSyncResultRead,
    summary=(
        "Обновление поля load_percent по данным Prometheus (среднее за заданный интервал времени)"
    ),
)
async def sync_load_from_prometheus(
    hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Длительность интервала усреднения, часов",
    ),
) -> ServerLoadSyncResultRead:
    return await run_in_threadpool(sync_load_from_prometheus_result, hours)


@router.post(
    "",
    response_model=ServerRead,
    status_code=201,
    summary="Создание записи сервера",
)
async def create_server_ep(body: ServerCreate, session: SessionDep) -> Server:
    return create_server(session, body, settings)


@router.post(
    "/sync-xray-clients",
    response_model=XrayClientsSyncResultRead,
    status_code=202,
    summary="Постановка в очередь RQ синхронизации списка клиентов Xray на всех готовых узлах",
)
async def enqueue_sync_xray_clients_all() -> XrayClientsSyncResultRead:
    return enqueue_sync_xray_all(settings)


@router.post(
    "/{server_id}/sync-xray-clients",
    response_model=XrayClientsSyncOneResultRead,
    status_code=202,
    summary="Постановка в очередь RQ синхронизации списка клиентов Xray на одном узле",
)
async def enqueue_sync_xray_clients_one(
    server_id: int,
    session: ReadonlySessionDep,
) -> XrayClientsSyncOneResultRead:
    return enqueue_sync_xray_one(session, server_id, settings)


@router.post(
    "/{server_id}/provision",
    response_model=ServerRead,
    status_code=202,
    summary="Постановка в очередь RQ полной установки ПО на узле",
)
async def enqueue_server_provision(server_id: int, session: SessionDep) -> Server:
    return enqueue_full_provision(session, server_id, settings)


@router.post(
    "/{server_id}/provision/reset",
    response_model=ServerRead,
    status_code=200,
    summary="Сброс статуса provision (queued или running) и отмена связанной задачи RQ",
)
async def reset_server_provision_ep(server_id: int, session: SessionDep) -> Server:
    return reset_server_provision(session, server_id)


@router.post(
    "/{server_id}/provision/reconcile",
    response_model=ServerRead,
    status_code=202,
    summary="Повторный прогон сценария установки (Xray и node_exporter) без предварительного сброса готовности",
)
async def enqueue_server_reconcile_ep(server_id: int, session: SessionDep) -> Server:
    return enqueue_server_reconcile(session, server_id, settings)


@router.post(
    "/{server_id}/provision/xray",
    response_model=ServerRead,
    status_code=202,
    summary="Установка и настройка только Xray на узле",
)
async def enqueue_server_provision_xray(server_id: int, session: SessionDep) -> Server:
    return enqueue_component_install(session, server_id, component="xray", cfg=settings)


@router.post(
    "/{server_id}/provision/prometheus",
    response_model=ServerRead,
    status_code=202,
    summary="Установка и настройка только node_exporter на узле",
)
async def enqueue_server_provision_prometheus(server_id: int, session: SessionDep) -> Server:
    return enqueue_component_install(session, server_id, component="prometheus", cfg=settings)


@router.post(
    "/{server_id}/provision/fair-egress",
    response_model=ServerRead,
    status_code=202,
    summary="Настройка справедливой очереди на uplink (CAKE или fq_codel)",
)
async def enqueue_server_provision_fair_egress(server_id: int, session: SessionDep) -> Server:
    return enqueue_component_install(session, server_id, component="fair_egress", cfg=settings)


@router.post(
    "/{server_id}/provision/cleanup",
    response_model=ServerRead,
    status_code=202,
    summary="Удаление Xray и node_exporter с узла и очистка связанных полей в базе данных",
)
async def enqueue_server_provision_cleanup(server_id: int, session: SessionDep) -> Server:
    return enqueue_component_install(session, server_id, component="cleanup", cfg=settings)


@router.patch(
    "/{server_id}",
    response_model=ServerRead,
    summary="Частичное обновление параметров сервера",
)
async def patch_server_ep(server_id: int, body: ServerUpdate, session: SessionDep) -> Server:
    return patch_server(session, server_id, body)


@router.get(
    "/{server_id}/ping",
    response_model=ServerPingRead,
    summary="Проверка доступности узла: порт VPN, каскад при наличии, экспорт метрик",
)
async def ping_server_reachable(
    server_id: int,
    session: ReadonlySessionDep,
    timeout_sec: float = Query(
        5.0,
        ge=0.5,
        le=15.0,
        description="Таймаут установки TCP-соединения, с",
    ),
) -> ServerPingRead:
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    host = (server.host or "").strip()
    port = int(server.port)
    ex_host: str | None = None
    ex_port: int | None = None
    if server.is_cascade_ru_entry and server.cascade_next_server_id is not None:
        ex = session.get(Server, int(server.cascade_next_server_id))
        if ex is not None:
            ex_host = (ex.host or "").strip() or None
            ex_port = int(ex.port)

    def _run():
        return tcp_probes_payload(
            host=host,
            port=port,
            exit_host=ex_host,
            exit_port=ex_port,
            timeout_sec=timeout_sec,
            cfg=settings,
        )

    tcp = await run_in_threadpool(_run)
    return build_server_health_read(
        session,
        server,
        settings,
        timeout_sec=timeout_sec,
        tcp=tcp,
    )


@router.delete(
    "/{server_id}",
    status_code=204,
    summary="Удаление сервера из базы данных и синхронизация списка клиентов на оставшихся узлах",
)
async def delete_server_ep(
    server_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> None:
    delete_server(session, server_id)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
