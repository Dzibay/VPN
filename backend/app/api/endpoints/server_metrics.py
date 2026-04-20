"""
История метрик узла из Prometheus (node_exporter).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep, require_admin
from app.core.config import settings
from app.core.queue import get_install_queue, get_redis
from app.database.session import SessionLocal
from app.models.server import Server
from app.schemas.server_metrics import (
    ServerMetricPoint,
    ServerMetricsAxisHints,
    ServerMetricsFromPrometheus,
)
from app.schemas.server_traffic import (
    ServerUserTrafficBundle,
    UserTrafficCollectDetail,
    UserTrafficCollectEnqueueResponse,
    UserTrafficCollectPollResponse,
)
from app.services.xray_stats_collect import load_user_traffic_bundle_rows
from app.services.bottleneck_metrics import enrich_bottleneck_metrics
from app.services.prometheus_node import (
    fetch_analytics_axis_hints,
    fetch_instant_scalar,
    fetch_node_metrics_merged,
    format_query_with_instance,
)

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
            enrich_bottleneck_metrics(
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


def _rq_poll_status(job: Job) -> str:
    st = job.get_status()
    if st in (
        JobStatus.QUEUED,
        JobStatus.SCHEDULED,
        JobStatus.CREATED,
        JobStatus.DEFERRED,
    ):
        return "queued"
    if st == JobStatus.STARTED:
        return "started"
    if st == JobStatus.FINISHED:
        return "finished"
    if st in (JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED):
        return "failed"
    return "queued"


@router.post(
    "/{server_id}/user-traffic/collect",
    response_model=UserTrafficCollectEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
    summary="Поставить в очередь RQ сбор трафика Xray по SSH (выполняет воркер, как провижининг)",
)
async def enqueue_user_traffic_collect(
    server_id: int,
    session: SessionDep,
) -> UserTrafficCollectEnqueueResponse:
    if session.get(Server, server_id) is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    job_timeout = max(300, int(settings.xray_stats_ssh_timeout_seconds) + 120)
    try:
        q = get_install_queue()
        job = q.enqueue(
            "worker.jobs.collect_xray_user_traffic",
            server_id,
            job_timeout=job_timeout,
        )
    except RedisError as e:
        log.exception("Redis/RQ недоступен (сбор трафика)")
        raise HTTPException(
            status_code=503,
            detail=f"Очередь недоступна: {e}",
        ) from e
    return UserTrafficCollectEnqueueResponse(server_id=server_id, job_id=job.id)


@router.get(
    "/{server_id}/user-traffic/collect-jobs/{job_id}",
    response_model=UserTrafficCollectPollResponse,
    dependencies=[Depends(require_admin)],
    summary="Статус задачи сбора трафика (RQ) и результат после завершения",
)
async def poll_user_traffic_collect_job(
    server_id: int,
    job_id: str,
    session: SessionDep,
) -> UserTrafficCollectPollResponse:
    if session.get(Server, server_id) is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    try:
        job = Job.fetch(job_id, connection=get_redis())
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Задача не найдена") from None
    if not job.args or job.args[0] != server_id:
        raise HTTPException(status_code=404, detail="Задача не относится к этому серверу")

    status = _rq_poll_status(job)
    if status in ("queued", "started"):
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status=status,  # type: ignore[arg-type]
            bundle=None,
            job_error=None,
        )

    def _bundle_from_result(result: dict | None) -> ServerUserTrafficBundle:
        db = SessionLocal()
        try:
            detail = None
            if result and result.get("detail"):
                detail = UserTrafficCollectDetail.model_validate(result["detail"])
            collected_at = None
            raw_ca = (result or {}).get("collected_at")
            if raw_ca:
                collected_at = datetime.fromisoformat(
                    str(raw_ca).replace("Z", "+00:00"),
                )
            return load_user_traffic_bundle_rows(
                db,
                server_id,
                collected_at=collected_at,
                collect_error=(result or {}).get("error"),
                collect_detail=detail,
            )
        finally:
            db.close()

    if status == "failed":
        err_txt = None
        try:
            job.refresh()
            err_txt = (job.exc_info or str(job.result) or "Задача завершилась с ошибкой")[
                :8000
            ]
        except Exception:
            err_txt = "Задача завершилась с ошибкой"
        bundle = _bundle_from_result(None)
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status="failed",
            bundle=bundle,
            job_error=err_txt,
        )

    # finished
    result = job.result
    if not isinstance(result, dict):
        bundle = _bundle_from_result(None)
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status="finished",
            bundle=bundle.model_copy(
                update={
                    "collect_error": "Неверный результат задачи воркера",
                },
            ),
            job_error=None,
        )
    bundle = _bundle_from_result(result)
    return UserTrafficCollectPollResponse(
        server_id=server_id,
        job_id=job_id,
        status="finished",
        bundle=bundle,
        job_error=None,
    )


@router.get(
    "/{server_id}/user-traffic",
    response_model=ServerUserTrafficBundle,
    dependencies=[Depends(require_admin)],
    summary="Трафик по пользователям из БД (сбор с узла — POST …/user-traffic/collect, воркер RQ)",
)
async def get_server_user_traffic(
    server_id: int,
    session: SessionDep,
    response: Response,
    collect: bool = Query(
        False,
        description="Устарело: SSH не выполняется в API. Используйте POST …/user-traffic/collect",
    ),
) -> ServerUserTrafficBundle:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    if session.get(Server, server_id) is None:
        raise HTTPException(status_code=404, detail="Сервер не найден")
    if collect:
        raise HTTPException(
            status_code=400,
            detail=(
                "Сбор по SSH выполняет воркер RQ: "
                "POST /api/servers/{id}/user-traffic/collect, затем GET "
                "/api/servers/{id}/user-traffic/collect-jobs/{job_id}"
            ),
        )

    def _run() -> ServerUserTrafficBundle:
        db = SessionLocal()
        try:
            server = db.get(Server, server_id)
            if server is None:
                raise RuntimeError("server disappeared")
            return load_user_traffic_bundle_rows(db, server_id)
        finally:
            db.close()

    return await run_in_threadpool(_run)
