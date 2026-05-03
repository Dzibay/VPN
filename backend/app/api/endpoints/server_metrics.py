"""
История метрик узла из Prometheus (node_exporter).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, require_admin
from app.domain.models.server_metrics import ServerMetricsFromPrometheus
from app.domain.models.server_traffic import (
    ServerUserTrafficBundle,
    UserTrafficCollectAllEnqueueResponse,
    UserTrafficCollectEnqueueResponse,
    UserTrafficCollectPollResponse,
)
from app.domain.services.http_errors import HttpServiceError
from app.domain.services import server_metrics_service

router = APIRouter(prefix="/servers", tags=["admin"])


def _raise_svc(exc: HttpServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/user-traffic/collect-all",
    response_model=UserTrafficCollectAllEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
    summary="Постановка в очередь RQ пакетного сбора трафика Xray по всем узлам в состоянии provision_ready",
)
async def enqueue_user_traffic_collect_all() -> UserTrafficCollectAllEnqueueResponse:
    try:
        return await run_in_threadpool(server_metrics_service.enqueue_user_traffic_collect_all)
    except HttpServiceError as e:
        _raise_svc(e)


@router.get(
    "/{server_id}/metrics",
    response_model=ServerMetricsFromPrometheus,
    dependencies=[Depends(require_admin)],
    summary="Временные ряды метрик узла из Prometheus (node_exporter)",
)
async def get_server_metrics_prometheus(
    server_id: int,
    session: ReadonlySessionDep,
    hours: int = Query(24, ge=1, le=720, description="Глубина выборки, часов"),
    step: int = Query(60, ge=15, le=300, description="Интервал между точками ряда, с"),
) -> ServerMetricsFromPrometheus:
    try:
        inst, adj_step, tariff_cap = server_metrics_service.resolve_prometheus_metrics_inputs(
            session,
            server_id,
            hours,
            step,
            settings,
        )
    except HttpServiceError as e:
        _raise_svc(e)

    def _run():
        return server_metrics_service.fetch_merged_metrics_for_instance(
            inst,
            hours=hours,
            adj_step=adj_step,
            tariff_cap=tariff_cap,
            cfg=settings,
        )

    try:
        raw_points, used_step, axis_hints, online_clients_val, online_from_cfg = (
            await run_in_threadpool(_run)
        )
    except HttpServiceError as e:
        _raise_svc(e)

    return server_metrics_service.build_server_metrics_response(
        inst,
        raw_points,
        used_step,
        axis_hints,
        online_clients_val,
        online_from_cfg,
    )


@router.post(
    "/{server_id}/user-traffic/collect",
    response_model=UserTrafficCollectEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
    summary="Постановка в очередь RQ сбора трафика Xray по SSH для одного узла",
)
async def enqueue_user_traffic_collect(
    server_id: int,
    session: ReadonlySessionDep,
) -> UserTrafficCollectEnqueueResponse:
    try:
        return server_metrics_service.enqueue_user_traffic_collect_one(session, server_id, settings)
    except HttpServiceError as e:
        _raise_svc(e)


@router.get(
    "/{server_id}/user-traffic/collect-jobs/{job_id}",
    response_model=UserTrafficCollectPollResponse,
    dependencies=[Depends(require_admin)],
    summary="Состояние задачи RQ сбора трафика и результат после завершения",
)
async def poll_user_traffic_collect_job(
    server_id: int,
    job_id: str,
    session: ReadonlySessionDep,
) -> UserTrafficCollectPollResponse:
    try:
        return server_metrics_service.poll_user_traffic_collect_job_sync(session, server_id, job_id)
    except HttpServiceError as e:
        _raise_svc(e)


@router.get(
    "/{server_id}/user-traffic",
    response_model=ServerUserTrafficBundle,
    dependencies=[Depends(require_admin)],
    summary="Трафик по пользователям на узле из базы данных",
)
async def get_server_user_traffic(
    server_id: int,
    session: ReadonlySessionDep,
    response: Response,
    collect: bool = Query(
        False,
        description="Устаревший параметр; сбор выполняется только через POST …/user-traffic/collect",
    ),
) -> ServerUserTrafficBundle:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    def _run():
        return server_metrics_service.server_user_traffic_bundle_db_only(
            server_id,
            collect=collect,
        )

    try:
        return await run_in_threadpool(_run)
    except HttpServiceError as e:
        _raise_svc(e)
