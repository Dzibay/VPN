"""
История метрик узла из Prometheus (node_exporter).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, require_admin
from app.domain.models.server_metrics import ServerMetricsFromPrometheus, ServerWarpStatusRead
from app.domain.models.server_traffic import (
    AllServersInboundTrafficDailySummary,
    ServerTrafficDailySummary,
    ServerUserTrafficBundle,
    UserTrafficCollectAllEnqueueResponse,
    UserTrafficCollectEnqueueResponse,
    UserTrafficCollectPollResponse,
)
from app.domain.services import server_metrics_service

router = APIRouter(prefix="/servers", tags=["admin"])


@router.post(
    "/user-traffic/collect-all",
    response_model=UserTrafficCollectAllEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
    summary="Постановка в очередь RQ пакетного сбора трафика Xray по всем узлам в состоянии provision_ready",
)
async def enqueue_user_traffic_collect_all() -> UserTrafficCollectAllEnqueueResponse:
    return server_metrics_service.enqueue_user_traffic_collect_all()


@router.get(
    "/user-traffic/daily-summary-all",
    response_model=AllServersInboundTrafficDailySummary,
    dependencies=[Depends(require_admin)],
    summary="Дневной ряд входящего трафика (down_bytes) по узлам и суммарно; exit_server_ids — каскадные exit",
)
async def get_all_servers_inbound_traffic_daily_summary(
    response: Response,
    days: int = Query(
        90,
        ge=1,
        le=366,
        description="Глубина окна в календарных днях UTC от сегодня включительно",
    ),
) -> AllServersInboundTrafficDailySummary:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return await server_metrics_service.all_servers_inbound_traffic_daily_db_only(days=days)


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
    inst, adj_step, tariff_cap = await server_metrics_service.resolve_prometheus_metrics_inputs(
        session,
        server_id,
        hours,
        step,
        settings,
    )

    raw_points, used_step, axis_hints, online_clients_val, online_from_cfg = (
        await server_metrics_service.fetch_merged_metrics_for_instance(
            inst,
            hours=hours,
            adj_step=adj_step,
            tariff_cap=tariff_cap,
            cfg=settings,
        )
    )

    return server_metrics_service.build_server_metrics_response(
        inst,
        raw_points,
        used_step,
        axis_hints,
        online_clients_val,
        online_from_cfg,
    )


@router.get(
    "/{server_id}/warp-status",
    response_model=ServerWarpStatusRead,
    dependencies=[Depends(require_admin)],
    summary="Cloudflare WARP: состояние, лимиты и метрики из Prometheus",
)
async def get_server_warp_status(
    server_id: int,
    session: ReadonlySessionDep,
    response: Response,
) -> ServerWarpStatusRead:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return await server_metrics_service.get_server_warp_status(session, server_id, cfg=settings)


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
    return await server_metrics_service.enqueue_user_traffic_collect_one(session, server_id, settings)


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
    return await server_metrics_service.poll_user_traffic_collect_job_sync(session, server_id, job_id)


@router.get(
    "/{server_id}/user-traffic/daily-summary",
    response_model=ServerTrafficDailySummary,
    dependencies=[Depends(require_admin)],
    summary="Дневной ряд: накопление суточных приростов трафика по узлу (перенос снимков, все даты UTC)",
)
async def get_server_user_traffic_daily_summary(
    server_id: int,
    _session: ReadonlySessionDep,
    response: Response,
    days: int = Query(
        90,
        ge=1,
        le=366,
        description="Глубина окна в календарных днях UTC от сегодня включительно",
    ),
) -> ServerTrafficDailySummary:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return await server_metrics_service.server_traffic_daily_summary_db_only(server_id, days=days)


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
    return await server_metrics_service.server_user_traffic_bundle_db_only(
        server_id,
        collect=collect,
    )
