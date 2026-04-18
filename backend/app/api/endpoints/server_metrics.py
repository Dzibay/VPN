"""
История метрик узла из Prometheus (node_exporter).
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep, require_admin
from app.models.server import Server
from app.schemas.server_metrics import ServerMetricPoint, ServerMetricsFromPrometheus
from app.services.prometheus_node import fetch_node_metrics_merged

log = logging.getLogger("app.server_metrics")

router = APIRouter(prefix="/servers", tags=["server-metrics"])


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
        inst = f"{server.host.strip()}:9100"

    adj_step = step
    est_points = (hours * 3600) // adj_step
    if est_points > 2500:
        adj_step = max(15, (hours * 3600) // 2500)

    try:

        def _run() -> tuple[list[dict], int]:
            return fetch_node_metrics_merged(
                inst,
                hours=hours,
                step_seconds=adj_step,
            )

        raw_points, used_step = await run_in_threadpool(_run)
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
        points=points,
    )
