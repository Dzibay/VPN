"""Доступность узлов: агрегаты фонового TCP-опроса (данные лежат в Redis).

Сами пробы выполняет фоновый планировщик; здесь — разовая сетевая проба для ручной проверки
(:func:`tcp_probes_payload`) и чтение/агрегация накопленной истории из Redis.
"""

from __future__ import annotations

from typing import Any

from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.domain.models.servers import (
    ServerReachabilityHistoryRead,
    ServerReachabilitySampleRead,
    ServerReachabilitySummaryRowRead,
    ServersReachabilitySummaryRead,
)
from app.domain.servers.traffic_archive import TRAFFIC_ARCHIVE_SERVER_ID
from app.infrastructure.cache import get_redis
from app.infrastructure.cache.server_reachability_store import (
    fetch_server_reachability_history,
    pipeline_fetch_reachability_histories,
)
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.server_health_check import run_tcp_probes


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
