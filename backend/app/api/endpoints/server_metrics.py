"""
История метрик узла из Prometheus (node_exporter).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep, require_admin
from app.core.config import settings
from app.models.server import Server
from app.schemas.server_metrics import (
    ServerMetricPoint,
    ServerMetricsAxisHints,
    ServerMetricsFromPrometheus,
)
from app.services.prometheus_node import (
    fetch_analytics_axis_hints,
    fetch_instant_scalar,
    fetch_node_metrics_merged,
    format_query_with_instance,
)

log = logging.getLogger("app.server_metrics")

router = APIRouter(prefix="/servers", tags=["server-metrics"])


def _enrich_bottleneck_metrics(
    points: list[dict[str, Any]],
    *,
    cap_mbps: float | None,
    cpu_cores: int | None,
) -> None:
    cap = float(cap_mbps) if cap_mbps is not None and cap_mbps > 0 else None
    cores = int(cpu_cores) if cpu_cores is not None and cpu_cores >= 1 else None
    for p in points:
        parts: list[float] = []
        for key in ("cpu_percent", "memory_percent", "disk_used_percent"):
            v = p.get(key)
            if v is not None:
                parts.append(float(v))
        net_u: float | None = None
        if cap is not None:
            rx = p.get("net_rx_mbps")
            tx = p.get("net_tx_mbps")
            if rx is not None or tx is not None:
                peak = max(float(rx or 0), float(tx or 0))
                net_u = min(100.0, 100.0 * peak / cap)
                parts.append(net_u)
        p["net_util_percent"] = net_u
        load_u: float | None = None
        if cores is not None:
            load1 = p.get("load_avg_1m")
            if load1 is not None:
                load_u = min(100.0, 100.0 * float(load1) / cores)
                parts.append(load_u)
        p["load_util_percent"] = load_u
        p["bottleneck_percent"] = max(parts) if parts else None


@router.get(
    "/{server_id}/metrics",
    response_model=ServerMetricsFromPrometheus,
    dependencies=[Depends(require_admin)],
    summary="Метрики узла из Prometheus (node_exporter, query_range)",
)
async def get_server_metrics_prometheus(
    server_id: int,
    session: SessionDep,
    hours: int = Query(24, ge=1, le=720, description="Глубина, часов"),
    step: int = Query(60, ge=15, le=300, description="Шаг разрешения, сек"),
) -> ServerMetricsFromPrometheus:
    server = session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")

    inst = (server.prometheus_instance or "").strip()
    if not inst:
        inst = f"{server.host.strip()}:{settings.provision_node_exporter_port}"

    adj_step = step
    est_points = (hours * 3600) // adj_step
    if est_points > 2500:
        adj_step = max(15, (hours * 3600) // 2500)

    tariff_cap = server.network_cap_mbps

    try:

        def _run() -> tuple[list[dict], int, ServerMetricsAxisHints, int | None, bool]:
            raw, step = fetch_node_metrics_merged(
                inst,
                hours=hours,
                step_seconds=adj_step,
            )
            hints_raw = fetch_analytics_axis_hints(inst)
            nic_mbps = hints_raw.get("nic_mbps")
            if tariff_cap is not None and tariff_cap > 0:
                chart_net_mbps = float(tariff_cap)
            else:
                chart_net_mbps = nic_mbps
            loads = [p["load_avg_1m"] for p in raw if p.get("load_avg_1m") is not None]
            tcps = [p["tcp_established"] for p in raw if p.get("tcp_established") is not None]
            cores = hints_raw.get("cpu_cores")
            load_max_d = max(loads) if loads else None
            load_y_max = max((cores or 1) * 1.2, (load_max_d or 0) * 1.15, 1.0)
            tcp_max_d = max(tcps) if tcps else None
            tcp_y_max = max((tcp_max_d or 0) * 1.2, 16.0)
            axis = ServerMetricsAxisHints(
                network_max_mbps=chart_net_mbps,
                network_tariff_mbps=tariff_cap,
                network_nic_mbps=nic_mbps,
                cpu_cores=hints_raw.get("cpu_cores"),
                load_y_max=round(load_y_max, 2),
                tcp_y_max=round(tcp_y_max, 2),
            )
            _enrich_bottleneck_metrics(
                raw,
                cap_mbps=chart_net_mbps,
                cpu_cores=cores,
            )
            oc_template = (settings.prometheus_online_clients_query or "").strip()
            online_from_cfg = bool(oc_template)
            online_clients: int | None = None
            if online_from_cfg:
                q = format_query_with_instance(oc_template, inst)
                v = fetch_instant_scalar(q)
                if v is not None:
                    try:
                        online_clients = max(0, int(round(float(v))))
                    except (TypeError, ValueError):
                        online_clients = None
            return raw, step, axis, online_clients, online_from_cfg

        raw_points, used_step, axis_hints, online_clients_val, online_from_cfg = (
            await run_in_threadpool(_run)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPError as e:
        log.warning("Prometheus HTTP error: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось запросить Prometheus: {e}",
        ) from e

    points = [ServerMetricPoint.model_validate(p) for p in raw_points]
    return ServerMetricsFromPrometheus(
        instance=inst,
        step_seconds=used_step,
        axis=axis_hints,
        online_clients=online_clients_val,
        online_clients_from_prometheus=online_from_cfg,
        points=points,
    )
