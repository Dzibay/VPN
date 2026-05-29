"""Управление серверами: CRUD-операции и оркестрация очередей установки/синхронизации.

Низкоуровневые примитивы лежат в пакете :mod:`app.domain.servers`:

* каскадные инварианты — :mod:`app.domain.servers.cascade`,
* очередь установки ПО — :mod:`app.domain.servers.provision_queue`,
* дефолты REALITY/VLESS — :mod:`app.domain.servers.reality_defaults`.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Any

from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from rq.job import Job
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.domain.models.servers import (
    ServerCreate,
    ServerLoadSyncItemRead,
    ServerLoadSyncResultRead,
    ServerReachabilityHistoryRead,
    ServerReachabilitySampleRead,
    ServerReachabilitySummaryRowRead,
    ServersReachabilitySummaryRead,
    ServerUpdate,
    ServersCountResponse,
    XrayClientsSyncOneResultRead,
    XrayClientsSyncResultRead,
)
from app.domain.servers.cascade import (
    merge_cascade_fields,
    try_enqueue_sync_xray_on_exit_for_cascade,
    validate_cascade_pair,
)
from app.domain.servers.provision_queue import (
    enqueue_software_job,
    provision_command_blocks_split_install,
)
from app.domain.servers.reality_defaults import reality_defaults_for_create
from app.domain.servers.traffic_archive import (
    assert_deletable_server_id,
    ensure_traffic_archive_server,
    relocate_server_traffic_to_archive,
    TRAFFIC_ARCHIVE_SERVER_ID,
)
from app.domain.users.xray_sync_queue import (
    ensure_sync_xray_clients_all_servers_enqueued,
    ensure_sync_xray_clients_to_server_enqueued,
)
from app.infrastructure.cache import get_redis
from app.infrastructure.cache.server_reachability_store import (
    delete_server_reachability_key,
    fetch_server_reachability_history,
    pipeline_fetch_reachability_histories,
)
from app.infrastructure.database.operations import table_insert
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.prometheus.server_load_sync import sync_all_servers_load_from_prometheus
from app.infrastructure.server_health_check import run_tcp_probes

log = logging.getLogger("app.servers_service")


async def servers_count(session: AsyncSession) -> ServersCountResponse:
    """Общее число записей в таблице ``servers`` (без служебного архива id=0)."""
    total = await session.scalar(
        select(func.count())
        .select_from(Server)
        .where(Server.id != TRAFFIC_ARCHIVE_SERVER_ID),
    )
    return ServersCountResponse(servers_count=int(total or 0))


async def list_servers(session: AsyncSession) -> list[Server]:
    """Список всех серверов; новейшие первыми (для админки)."""
    stmt = (
        select(Server)
        .where(Server.id != TRAFFIC_ARCHIVE_SERVER_ID)
        .order_by(Server.id.desc())
    )
    return list((await session.scalars(stmt)).all())


def _sync_load_from_prometheus_blocking(hours: int) -> ServerLoadSyncResultRead:
    """Синхронная реализация: открывает свою sync-сессию и крутит httpx (запросы Prometheus).

    Вызывать только из ``run_in_threadpool`` — внутри нет ``await`` точек.
    """
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


async def sync_load_from_prometheus_result(hours: int) -> ServerLoadSyncResultRead:
    """Подтянуть текущую нагрузку узлов из Prometheus (среднее за последние ``hours`` часов).

    Внутри: sync httpx + sync SQLAlchemy (см. ``infrastructure.prometheus.server_load_sync``);
    обёрнуто в threadpool, чтобы не блокировать event loop API на время запросов.
    """
    return await run_in_threadpool(_sync_load_from_prometheus_blocking, hours)


async def create_server(
    session: AsyncSession, body: ServerCreate, cfg: Settings | None = None,
) -> Server:
    """Создать запись сервера; недостающие REALITY/VLESS-поля заполняются дефолтами."""
    cfg = cfg or settings
    defaults = reality_defaults_for_create(body)
    is_ru = bool(body.is_cascade_ru_entry)
    cnext = body.cascade_next_server_id
    if cnext is not None:
        is_ru = True
    elif not is_ru:
        cnext = None
    if body.proxy_kind in ("hysteria2", "vless_grpc") and (is_ru or cnext is not None):
        raise ConflictError(
            "Hysteria2 и VLESS gRPC пока не поддерживают каскад; используйте VLESS+REALITY",
        )
    await validate_cascade_pair(session, self_id=None, is_ru_entry=is_ru, cascade_next_id=cnext)
    cascade_egress_uuid: str | None = str(uuid_lib.uuid4()) if cnext else None
    server = Server(
        name=body.name,
        host=body.host,
        port=body.port,
        country=body.country,
        load_percent=body.load_percent,
        is_active=body.is_active,
        whitelist=body.whitelist,
        include_in_auto=body.include_in_auto,
        is_hidden=body.is_hidden,
        prometheus_instance=body.prometheus_instance,
        network_cap_mbps=body.network_cap_mbps,
        is_cascade_ru_entry=is_ru,
        cascade_next_server_id=cnext,
        cascade_egress_client_uuid=cascade_egress_uuid,
        proxy_kind=body.proxy_kind,
        **defaults,
    )
    try:
        await table_insert(session, server)
    except IntegrityError as e:
        log.warning("create_server conflict: %s", e)
        raise ConflictError(
            "Сервер с таким host и port уже существует",
        ) from e
    await try_enqueue_sync_xray_on_exit_for_cascade(session, cnext)
    return server


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
    if (server.proxy_kind or "vless").strip().lower() not in ("vless", "vless_grpc"):
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


async def patch_server(session: AsyncSession, server_id: int, body: ServerUpdate) -> Server:
    """Частичное обновление сервера; cascade-поля валидируются совместно.

    Замена ``reality_private_key`` обнуляет публичный ключ — он будет пересчитан воркером.
    Изменение cascade-связки порождает sync Xray на старом и новом exit-узлах.
    """
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return server
    if data.get("reality_spider_x") is None and "reality_spider_x" in data:
        data["reality_spider_x"] = "/"
    priv_in = data.get("reality_private_key")
    if priv_in:
        new_priv = str(priv_in).strip()
        old_priv = (server.reality_private_key or "").strip()
        if new_priv != old_priv:
            server.reality_public_key = None
    if data.get("proxy_kind") in ("hysteria2", "vless_grpc"):
        data["reality_public_key"] = None
    cascade_touched = False
    old_cnext: int | None = None
    if "is_cascade_ru_entry" in data or "cascade_next_server_id" in data:
        cascade_touched = True
        old_cnext = server.cascade_next_server_id
        old_cuuid = server.cascade_egress_client_uuid
        is_ru, cnext = merge_cascade_fields(server, data)
        await validate_cascade_pair(
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
    final_proxy = data.get("proxy_kind", server.proxy_kind or "vless")
    final_is_ru = bool(data.get("is_cascade_ru_entry", server.is_cascade_ru_entry))
    final_cnext = data.get("cascade_next_server_id", server.cascade_next_server_id)
    if final_proxy in ("hysteria2", "vless_grpc") and (final_is_ru or final_cnext is not None):
        raise ConflictError(
            "Hysteria2 и VLESS gRPC пока не поддерживают каскад; используйте VLESS+REALITY",
        )
    for key, value in data.items():
        setattr(server, key, value)
    await session.flush()
    if cascade_touched:
        await try_enqueue_sync_xray_on_exit_for_cascade(
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
    """Только сетевые TCP-пробы; без обращения к БД (можно вызывать из ``run_in_threadpool``)."""
    cfg = cfg or settings
    return run_tcp_probes(
        host,
        port,
        ne_port=int(cfg.provision_node_exporter_port),
        exit_host=exit_host,
        exit_port=exit_port,
        timeout_sec=timeout_sec,
    )


def _aggregate_reachability_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {
            "samples_total": 0,
            "vpn_ok_count": 0,
            "vpn_ok_percent": 0.0,
            "last_probe_ts": None,
            "last_vpn_ok": None,
            "avg_vpn_latency_ms": None,
            "ne_ok_percent": None,
            "exit_ok_percent": None,
        }
    vpn_ok = sum(1 for x in samples if x.get("vpn_ok"))
    latencies = [
        float(x["vpn_ms"])
        for x in samples
        if x.get("vpn_ok") and x.get("vpn_ms") is not None
    ]
    avg_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
    last = samples[-1]
    last_ts_raw = last.get("ts")
    last_ts = float(last_ts_raw) if last_ts_raw is not None else None
    last_vpn_ok = bool(last["vpn_ok"]) if "vpn_ok" in last else None

    ne_samples = [x for x in samples if x.get("ne_ok") is not None]
    ne_pct = None
    if ne_samples:
        ne_ok_c = sum(1 for x in ne_samples if x.get("ne_ok"))
        ne_pct = round(100.0 * ne_ok_c / len(ne_samples), 1)

    exit_samples = [x for x in samples if x.get("exit_ok") is not None]
    exit_pct = None
    if exit_samples:
        ex_ok_c = sum(1 for x in exit_samples if x.get("exit_ok"))
        exit_pct = round(100.0 * ex_ok_c / len(exit_samples), 1)

    return {
        "samples_total": n,
        "vpn_ok_count": vpn_ok,
        "vpn_ok_percent": round(100.0 * vpn_ok / n, 1),
        "last_probe_ts": last_ts,
        "last_vpn_ok": last_vpn_ok,
        "avg_vpn_latency_ms": avg_ms,
        "ne_ok_percent": ne_pct,
        "exit_ok_percent": exit_pct,
    }


async def servers_reachability_summary(
    session: AsyncSession,
    *,
    hours: float,
) -> ServersReachabilitySummaryRead:
    """Сводные проценты и последний статус по всем серверам (Redis pipeline)."""
    stmt = (
        select(Server)
        .where(Server.id != TRAFFIC_ARCHIVE_SERVER_ID)
        .order_by(Server.id.asc())
    )
    servers = list((await session.scalars(stmt)).all())
    ids = [int(s.id) for s in servers]
    retention = int(settings.server_reachability_history_retention_seconds)

    def _redis_part() -> dict[int, list[dict[str, Any]]]:
        return pipeline_fetch_reachability_histories(
            get_redis(),
            ids,
            retention_seconds=retention,
            hours=hours,
        )

    try:
        by_id = await run_in_threadpool(_redis_part)
    except RedisError:
        raise ServiceUnavailableError("Redis недоступен") from None

    rows: list[ServerReachabilitySummaryRowRead] = []
    for s in servers:
        sid = int(s.id)
        samples = by_id.get(sid, [])
        a = _aggregate_reachability_samples(samples)
        rows.append(
            ServerReachabilitySummaryRowRead(
                server_id=sid,
                name=s.name,
                host=(s.host or "").strip(),
                port=int(s.port),
                is_active=bool(s.is_active),
                provision_ready=bool(s.provision_ready),
                samples_total=a["samples_total"],
                vpn_ok_count=a["vpn_ok_count"],
                vpn_ok_percent=a["vpn_ok_percent"],
                last_probe_ts=a["last_probe_ts"],
                last_vpn_ok=a["last_vpn_ok"],
                avg_vpn_latency_ms=a["avg_vpn_latency_ms"],
                ne_ok_percent=a["ne_ok_percent"],
                exit_ok_percent=a["exit_ok_percent"],
            )
        )

    return ServersReachabilitySummaryRead(
        hours_window=hours,
        probe_interval_seconds_hint=max(30, int(settings.server_reachability_interval_seconds)),
        servers=rows,
    )


async def delete_server(session: AsyncSession, server_id: int) -> None:
    """Удалить запись сервера; трафик пользователей переносится на служебный узел id=0."""
    assert_deletable_server_id(server_id)
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    await ensure_traffic_archive_server(session)
    moved = await relocate_server_traffic_to_archive(session, server_id)
    if moved:
        log.info(
            "delete_server: перенесено %s строк user_server_traffic server_id=%s → id=0",
            moved,
            server_id,
        )
    await session.delete(server)
    await session.flush()
    delete_server_reachability_key(get_redis(), server_id)


async def server_reachability_history(
    session: AsyncSession,
    server_id: int,
    *,
    hours: float,
) -> ServerReachabilityHistoryRead:
    """История фоновых TCP-проверок из Redis (окно не больше retention в настройках)."""
    srv = await session.get(Server, server_id)
    if srv is None:
        raise NotFoundError("Сервер не найден")

    def _read() -> list:
        return fetch_server_reachability_history(
            get_redis(),
            server_id,
            retention_seconds=int(settings.server_reachability_history_retention_seconds),
            hours=hours,
        )

    try:
        raw = await run_in_threadpool(_read)
    except RedisError:
        raise ServiceUnavailableError("Redis недоступен") from None

    samples: list[ServerReachabilitySampleRead] = []
    for row in raw:
        try:
            samples.append(ServerReachabilitySampleRead.model_validate(row))
        except Exception:
            continue
    return ServerReachabilityHistoryRead(server_id=server_id, samples=samples)
