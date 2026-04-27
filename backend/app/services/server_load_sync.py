"""
Запись servers.load_percent из Prometheus: среднее «узкое место» за окно (по умолчанию 24 ч).
Та же логика, что и график «Узкое место» в аналитике.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.server import Server
from app.services.bottleneck_metrics import enrich_bottleneck_metrics
from app.services.prometheus_node import (
    PROMETHEUS_BATCH_ABORT_DETAIL_PREFIX,
    fetch_analytics_axis_hints,
    fetch_node_metrics_merged,
    prometheus_batch_abort_detail,
)

log = logging.getLogger("app.server_load_sync")


@dataclass
class ServerLoadSyncItem:
    server_id: int
    host: str
    ok: bool
    load_percent: int | None = None
    detail: str = ""


@dataclass
class ServerLoadSyncReport:
    hours: int
    items: list[ServerLoadSyncItem] = field(default_factory=list)


def _instance_for_server(server: Server) -> str:
    inst = (server.prometheus_instance or "").strip()
    if not inst:
        inst = f"{server.host.strip()}:{settings.provision_node_exporter_port}"
    return inst


def sync_server_load_percent_from_prometheus(
    session: Session,
    server: Server,
    *,
    hours: int = 24,
    step_seconds: int = 120,
) -> ServerLoadSyncItem:
    """
    Среднее bottleneck_percent за окно → servers.load_percent (0–100).
    """
    if not (settings.prometheus_base_url or "").strip():
        return ServerLoadSyncItem(
            server_id=server.id,
            host=server.host,
            ok=False,
            detail=prometheus_batch_abort_detail("PROMETHEUS_BASE_URL не задан"),
        )

    inst = _instance_for_server(server)
    tariff_cap = server.network_cap_mbps

    try:
        raw, used_step = fetch_node_metrics_merged(
            inst,
            hours=hours,
            step_seconds=step_seconds,
        )
        hints_raw = fetch_analytics_axis_hints(inst)
        nic_mbps = hints_raw.get("nic_mbps")
        if tariff_cap is not None and tariff_cap > 0:
            chart_net_mbps: float | None = float(tariff_cap)
        else:
            chart_net_mbps = nic_mbps
        cores = hints_raw.get("cpu_cores")

        enrich_bottleneck_metrics(
            raw,
            cap_mbps=chart_net_mbps,
            cpu_cores=cores,
        )
        vals = [
            float(p["bottleneck_percent"])
            for p in raw
            if p.get("bottleneck_percent") is not None
        ]
        if not vals:
            return ServerLoadSyncItem(
                server_id=server.id,
                host=server.host,
                ok=False,
                detail="Нет точек bottleneck за период",
            )
        avg = sum(vals) / len(vals)
        new_load = int(max(0, min(100, round(avg))))
        server.load_percent = new_load
        session.commit()
        log.info(
            "load_percent synced server_id=%s host=%s -> %s (avg bottleneck, %s points, step=%ss)",
            server.id,
            server.host,
            new_load,
            len(vals),
            used_step,
        )
        return ServerLoadSyncItem(
            server_id=server.id,
            host=server.host,
            ok=True,
            load_percent=new_load,
            detail=f"среднее за {hours}ч, точек={len(vals)}",
        )
    except RuntimeError as e:
        session.rollback()
        return ServerLoadSyncItem(
            server_id=server.id,
            host=server.host,
            ok=False,
            detail=prometheus_batch_abort_detail(str(e)),
        )
    except httpx.HTTPError as e:
        session.rollback()
        log.warning("Prometheus sync load server_id=%s: %s", server.id, e)
        return ServerLoadSyncItem(
            server_id=server.id,
            host=server.host,
            ok=False,
            detail=prometheus_batch_abort_detail(f"Prometheus: {e}"),
        )
    except Exception as e:
        session.rollback()
        log.exception("sync load server_id=%s", server.id)
        return ServerLoadSyncItem(
            server_id=server.id,
            host=server.host,
            ok=False,
            detail=str(e),
        )


def sync_all_servers_load_from_prometheus(
    session: Session,
    *,
    hours: int = 24,
) -> ServerLoadSyncReport:
    report = ServerLoadSyncReport(hours=hours)
    stmt = select(Server).order_by(Server.id.asc())
    skip_remaining = False
    for server in session.scalars(stmt):
        if skip_remaining:
            report.items.append(
                ServerLoadSyncItem(
                    server_id=server.id,
                    host=server.host,
                    ok=False,
                    detail="Пропуск синхронизации: Prometheus недоступен (см. предыдущий узел в отчёте).",
                ),
            )
            continue
        item = sync_server_load_percent_from_prometheus(session, server, hours=hours)
        report.items.append(item)
        if not item.ok and (
            item.detail and PROMETHEUS_BATCH_ABORT_DETAIL_PREFIX in item.detail
        ):
            skip_remaining = True
    return report
