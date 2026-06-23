"""Метрики узлов из Prometheus и сбор трафика Xray (RQ)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx
from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.core.exceptions import (
    BadGatewayError,
    BadRequestError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.domain.models.server_metrics import (
    ServerMetricPoint,
    ServerMetricsAxisHints,
    ServerMetricsFromPrometheus,
    ServerWarpStatusRead,
)
from app.core.time import utc_today
from app.domain.models.server_traffic import (
    AllServersInboundTrafficDailySummary,
    ServerInboundTrafficDailySeries,
    ServerTrafficDailyPoint,
    ServerTrafficDailySummary,
    ServerUserTrafficBundle,
    UserTrafficCollectAllEnqueueResponse,
    UserTrafficCollectDetail,
    UserTrafficCollectEnqueueResponse,
    UserTrafficCollectPollResponse,
)
from app.infrastructure.cache import get_install_queue, get_redis
from app.infrastructure.database.blocking import run_blocking_with_session
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic
from app.infrastructure.prometheus.bottleneck_metrics import enrich_bottleneck_metrics
from app.infrastructure.prometheus.prometheus_node import (
    fetch_analytics_axis_hints,
    fetch_instant_scalar,
    fetch_node_metrics_merged,
    fetch_warp_status_from_prometheus,
    format_query_with_instance,
)
from app.infrastructure.xray.xray_stats_collect import load_user_traffic_bundle_rows
from app.infrastructure.xray.xray_traffic_scheduler import enqueue_xray_traffic_collect_batch_admin

log = logging.getLogger("app.server_metrics_service")


def enqueue_user_traffic_collect_all() -> UserTrafficCollectAllEnqueueResponse:
    try:
        job_id = enqueue_xray_traffic_collect_batch_admin()
    except RedisError as e:
        log.exception("Redis/RQ недоступен (батч-сбор трафика)")
        raise ServiceUnavailableError(f"Очередь недоступна: {e}") from e
    return UserTrafficCollectAllEnqueueResponse(job_id=job_id)


def _merged_metrics_worker(
    inst: str,
    *,
    hours: int,
    adj_step: int,
    tariff_cap: float | None,
    cfg: Settings,
) -> tuple[list[dict], int, ServerMetricsAxisHints, int | None, bool]:
    raw, step_used = fetch_node_metrics_merged(
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
    oc_template = (cfg.prometheus_online_clients_query or "").strip()
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
    return raw, step_used, axis, online_clients, online_from_cfg


async def resolve_prometheus_metrics_inputs(
    session: AsyncSession,
    server_id: int,
    hours: int,
    step: int,
    cfg: Settings | None = None,
) -> tuple[str, int, float | None]:
    cfg = cfg or settings
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")

    inst = (server.prometheus_instance or "").strip()
    if not inst:
        inst = f"{server.host.strip()}:{cfg.provision_node_exporter_port}"

    adj_step = step
    est_points = (hours * 3600) // adj_step
    if est_points > 2500:
        adj_step = max(15, (hours * 3600) // 2500)

    cap = server.network_cap_mbps
    tariff_cap = float(cap) if cap is not None else None
    return inst, adj_step, tariff_cap


def _warp_enabled_for_server(server: Server) -> bool:
    return (getattr(server, "google_routing_mode", None) or "exit").strip().lower() == "entry"


def _prometheus_instance_for_server(server: Server, cfg: Settings | None = None) -> str:
    cfg = cfg or settings
    inst = (server.prometheus_instance or "").strip()
    if not inst:
        inst = f"{server.host.strip()}:{cfg.provision_node_exporter_port}"
    return inst


def _format_bytes_human(n: int | float | None) -> str:
    if n is None:
        return "—"
    val = float(n)
    if val < 0:
        return "—"
    units = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"]
    i = 0
    while val >= 1024 and i < len(units) - 1:
        val /= 1024
        i += 1
    if i == 0:
        return f"{int(val)} {units[i]}"
    return f"{val:.1f} {units[i]}"


def _warp_status_detail(raw: dict[str, object]) -> str:
    if not raw.get("monitored"):
        return (
            "Метрики WARP не найдены в Prometheus. "
            "На узле: sync Xray / provision (entry), timer vpn-warp-check, node_exporter textfile."
        )
    parts: list[str] = []
    if raw.get("overall_ok"):
        parts.append("WARP в порядке")
    else:
        parts.append("Есть проблемы с WARP")
    if raw.get("account_type"):
        parts.append(f"аккаунт {raw['account_type']}")
    if raw.get("warp_plus"):
        parts.append("WARP+")
    quota = raw.get("quota_bytes")
    used = raw.get("premium_data_bytes")
    remaining = raw.get("quota_remaining_bytes")
    if quota is not None and used is not None:
        parts.append(
            f"лимит {_format_bytes_human(int(quota))}, "
            f"использовано {_format_bytes_human(int(used))}, "
            f"остаток {_format_bytes_human(int(remaining) if remaining is not None else None)}"
        )
    elif used is not None:
        parts.append(f"использовано premium {_format_bytes_human(int(used))}")
    else:
        parts.append("лимиты CF API не отдаются (типично для free WARP)")
    if raw.get("last_check_at") is not None:
        parts.append(f"проверка {raw['last_check_at']}")
    return ". ".join(parts) + "."


async def get_server_warp_status(
    session: AsyncSession,
    server_id: int,
    *,
    cfg: Settings | None = None,
) -> ServerWarpStatusRead:
    cfg = cfg or settings
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")

    enabled = _warp_enabled_for_server(server)
    inst = _prometheus_instance_for_server(server, cfg)
    if not enabled:
        return ServerWarpStatusRead(
            enabled=False,
            monitored=False,
            prometheus_instance=inst,
            detail=(
                "WARP не используется: google_routing_mode=exit. "
                "В карточке сервера выберите «Через вход (YouTube через Cloudflare WARP)» и нажмите Xray / Обновить всё."
            ),
        )

    try:
        raw = await run_in_threadpool(fetch_warp_status_from_prometheus, inst)
    except RuntimeError as e:
        raise ServiceUnavailableError(str(e)) from e
    except httpx.HTTPError as e:
        raise BadGatewayError(f"Не удалось запросить Prometheus: {e}") from e

    return ServerWarpStatusRead(
        enabled=True,
        monitored=bool(raw.get("monitored")),
        prometheus_instance=inst,
        overall_ok=raw.get("overall_ok"),
        profile_ok=raw.get("profile_ok"),
        outbound_ok=raw.get("outbound_ok"),
        endpoint_ok=raw.get("endpoint_ok"),
        cf_api_ok=raw.get("cf_api_ok"),
        warp_plus=raw.get("warp_plus"),
        youtube_probe_ok=raw.get("youtube_probe_ok"),
        probe_latency_ms=raw.get("probe_latency_ms"),
        last_check_at=raw.get("last_check_at"),
        account_type=raw.get("account_type"),
        license=raw.get("license"),
        quota_bytes=int(raw["quota_bytes"]) if raw.get("quota_bytes") is not None else None,
        premium_data_bytes=(
            int(raw["premium_data_bytes"]) if raw.get("premium_data_bytes") is not None else None
        ),
        quota_remaining_bytes=(
            int(raw["quota_remaining_bytes"])
            if raw.get("quota_remaining_bytes") is not None
            else None
        ),
        detail=_warp_status_detail(raw),
    )


async def fetch_merged_metrics_for_instance(
    inst: str,
    *,
    hours: int,
    adj_step: int,
    tariff_cap: float | None,
    cfg: Settings | None = None,
) -> tuple[list[dict], int, ServerMetricsAxisHints, int | None, bool]:
    """Запросы Prometheus делает sync httpx; обёрнуто в threadpool."""
    cfg = cfg or settings
    try:
        return await run_in_threadpool(
            _merged_metrics_worker,
            inst,
            hours=hours,
            adj_step=adj_step,
            tariff_cap=tariff_cap,
            cfg=cfg,
        )
    except RuntimeError as e:
        raise ServiceUnavailableError(str(e)) from e
    except httpx.HTTPError as e:
        log.warning("Prometheus HTTP error: %s", e)
        raise BadGatewayError(f"Не удалось запросить Prometheus: {e}") from e


def build_server_metrics_response(
    inst: str,
    raw_points: list[dict],
    used_step: int,
    axis_hints: ServerMetricsAxisHints,
    online_clients_val: int | None,
    online_from_cfg: bool,
) -> ServerMetricsFromPrometheus:
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


async def enqueue_user_traffic_collect_one(
    session: AsyncSession,
    server_id: int,
    cfg: Settings | None = None,
) -> UserTrafficCollectEnqueueResponse:
    cfg = cfg or settings
    if await session.get(Server, server_id) is None:
        raise NotFoundError("Сервер не найден")
    job_timeout = max(300, int(cfg.xray_stats_ssh_timeout_seconds) + 120)
    try:
        q = get_install_queue()
        job = q.enqueue(
            "app.worker.jobs.collect_xray_user_traffic",
            server_id,
            job_timeout=job_timeout,
        )
    except RedisError as e:
        log.exception("Redis/RQ недоступен (сбор трафика)")
        raise ServiceUnavailableError(f"Очередь недоступна: {e}") from e
    return UserTrafficCollectEnqueueResponse(server_id=server_id, job_id=job.id)


def _bundle_from_result_blocking(
    db: Session, server_id: int, result: dict | None,
) -> ServerUserTrafficBundle:
    """Sync SQL поверх переданной сессии — вызывать только из ``run_blocking_with_session``."""
    detail = None
    if result and result.get("detail"):
        detail = UserTrafficCollectDetail.model_validate(result["detail"])
    collected_at = None
    raw_ca = (result or {}).get("collected_at")
    if raw_ca:
        collected_at = datetime.fromisoformat(str(raw_ca).replace("Z", "+00:00"))
    return load_user_traffic_bundle_rows(
        db,
        server_id,
        collected_at=collected_at,
        collect_error=(result or {}).get("error"),
        collect_detail=detail,
    )


async def poll_user_traffic_collect_job_sync(
    session: AsyncSession,
    server_id: int,
    job_id: str,
) -> UserTrafficCollectPollResponse:
    if await session.get(Server, server_id) is None:
        raise NotFoundError("Сервер не найден")
    try:
        job = Job.fetch(job_id, connection=get_redis())
    except NoSuchJobError:
        raise NotFoundError("Задача не найдена") from None
    if not job.args or job.args[0] != server_id:
        raise NotFoundError("Задача не относится к этому серверу")

    status = _rq_poll_status(job)
    if status in ("queued", "started"):
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status=status,  # type: ignore[arg-type]
            bundle=None,
            job_error=None,
        )

    if status == "failed":
        err_txt = None
        try:
            job.refresh()
            err_txt = (job.exc_info or str(job.result) or "Задача завершилась с ошибкой")[:8000]
        except Exception:
            err_txt = "Задача завершилась с ошибкой"
        bundle = await run_blocking_with_session(_bundle_from_result_blocking, server_id, None)
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status="failed",
            bundle=bundle,
            job_error=err_txt,
        )

    result = job.result
    if not isinstance(result, dict):
        bundle = await run_blocking_with_session(_bundle_from_result_blocking, server_id, None)
        return UserTrafficCollectPollResponse(
            server_id=server_id,
            job_id=job_id,
            status="finished",
            bundle=bundle.model_copy(
                update={"collect_error": "Неверный результат задачи воркера"},
            ),
            job_error=None,
        )
    bundle = await run_blocking_with_session(_bundle_from_result_blocking, server_id, result)
    return UserTrafficCollectPollResponse(
        server_id=server_id,
        job_id=job_id,
        status="finished",
        bundle=bundle,
        job_error=None,
    )


def _server_user_traffic_bundle_db_only_blocking(
    db: Session, server_id: int,
) -> ServerUserTrafficBundle:
    """Sync SQL поверх переданной сессии. Вызывать из ``run_blocking_with_session``."""
    srv = db.get(Server, server_id)
    if srv is None:
        raise NotFoundError("Сервер не найден")
    return load_user_traffic_bundle_rows(db, server_id)


async def server_user_traffic_bundle_db_only(
    server_id: int, *, collect: bool,
) -> ServerUserTrafficBundle:
    if collect:
        raise BadRequestError(
            "Сбор по SSH выполняет воркер RQ: "
            "POST /api/servers/{id}/user-traffic/collect, затем GET "
            "/api/servers/{id}/user-traffic/collect-jobs/{job_id}",
        )
    return await run_blocking_with_session(_server_user_traffic_bundle_db_only_blocking, server_id)


def _inclusive_date_range(a: date, b: date) -> list[date]:
    out: list[date] = []
    d = a
    while d <= b:
        out.append(d)
        d += timedelta(days=1)
    return out


def _forward_fill_totals_on_grid(
    series: list[tuple[date, int]],
    grid: list[date],
) -> list[int]:
    """Для каждого дня из grid — последний total среди строк с traffic_date ≤ этого дня."""
    if not grid:
        return []
    out: list[int] = []
    pi = 0
    curr = 0
    for day in grid:
        while pi < len(series) and series[pi][0] <= day:
            curr = series[pi][1]
            pi += 1
        out.append(curr)
    return out


def _server_traffic_daily_summary_blocking(
    db: Session, server_id: int, days: int,
) -> ServerTrafficDailySummary:
    """Суточные дельты по переносу снимков на календарную сетку, сумма по пользователям, накопление и все дни подряд."""
    if db.get(Server, server_id) is None:
        raise NotFoundError("Сервер не найден")
    span = max(1, min(int(days), 366))
    today = utc_today()
    start = today - timedelta(days=span - 1)
    day_before_start = start - timedelta(days=1)

    stmt = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.traffic_date,
            (UserServerTraffic.up_bytes + UserServerTraffic.down_bytes).label("tot"),
        )
        .where(UserServerTraffic.server_id == server_id)
        .order_by(UserServerTraffic.user_id.asc(), UserServerTraffic.traffic_date.asc())
    )
    raw_rows = db.execute(stmt).all()

    by_user: dict[int, list[tuple[date, int]]] = defaultdict(list)
    for uid, traffic_d, tot in raw_rows:
        by_user[int(uid)].append((traffic_d, int(tot or 0)))

    grid = _inclusive_date_range(day_before_start, today)
    if not grid:
        return ServerTrafficDailySummary(server_id=server_id, points=[])

    if not by_user:
        points = [
            ServerTrafficDailyPoint(traffic_date=D, delta_sum_bytes=0, total_sum_bytes=0)
            for D in _inclusive_date_range(start, today)
        ]
        return ServerTrafficDailySummary(server_id=server_id, points=points)

    day_delta: dict[date, int] = defaultdict(int)
    for _uid, series in by_user.items():
        vals = _forward_fill_totals_on_grid(series, grid)
        for i in range(1, len(grid)):
            d = grid[i]
            if d < start:
                continue
            day_delta[d] += max(0, vals[i] - vals[i - 1])

    run = 0
    points: list[ServerTrafficDailyPoint] = []
    for d in _inclusive_date_range(start, today):
        dd = int(day_delta[d])
        run += dd
        points.append(
            ServerTrafficDailyPoint(
                traffic_date=d,
                delta_sum_bytes=dd,
                total_sum_bytes=run,
            ),
        )
    return ServerTrafficDailySummary(server_id=server_id, points=points)


async def server_traffic_daily_summary_db_only(
    server_id: int,
    *,
    days: int = 90,
) -> ServerTrafficDailySummary:
    return await run_blocking_with_session(_server_traffic_daily_summary_blocking, server_id, days)


def _daily_deltas_from_user_series(
    by_user: dict[int, list[tuple[date, int]]],
    grid: list[date],
    start: date,
) -> dict[date, int]:
    day_delta: dict[date, int] = defaultdict(int)
    for _uid, series in by_user.items():
        vals = _forward_fill_totals_on_grid(series, grid)
        for i in range(1, len(grid)):
            d = grid[i]
            if d < start:
                continue
            day_delta[d] += max(0, vals[i] - vals[i - 1])
    return day_delta


def _cascade_exit_server_ids(db: Session) -> list[int]:
    """Id узлов, на которые ссылается cascade_next_server_id (текущие exit в каскаде)."""
    rows = db.execute(
        select(Server.cascade_next_server_id)
        .where(Server.cascade_next_server_id.isnot(None))
        .distinct(),
    ).all()
    return sorted({int(r[0]) for r in rows if r[0] is not None})


def _all_servers_inbound_traffic_daily_blocking(
    db: Session,
    days: int,
) -> AllServersInboundTrafficDailySummary:
    """Суточные дельты down_bytes по узлам и суммарно (не накопительно)."""
    span = max(1, min(int(days), 366))
    today = utc_today()
    start = today - timedelta(days=span - 1)
    day_before_start = start - timedelta(days=1)
    grid = _inclusive_date_range(day_before_start, today)
    dates = _inclusive_date_range(start, today)
    if not grid:
        return AllServersInboundTrafficDailySummary()

    servers = db.execute(
        select(Server.id, Server.name, Server.host).order_by(Server.id.asc()),
    ).all()

    stmt = (
        select(
            UserServerTraffic.server_id,
            UserServerTraffic.user_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.down_bytes,
        )
        .order_by(
            UserServerTraffic.server_id.asc(),
            UserServerTraffic.user_id.asc(),
            UserServerTraffic.traffic_date.asc(),
        )
    )
    raw_rows = db.execute(stmt).all()

    by_server_user: dict[int, dict[int, list[tuple[date, int]]]] = defaultdict(
        lambda: defaultdict(list),
    )
    for sid_raw, uid_raw, traffic_d, down_raw in raw_rows:
        by_server_user[int(sid_raw)][int(uid_raw)].append(
            (traffic_d, int(down_raw or 0)),
        )

    total_by_day = {d: 0 for d in dates}
    server_series: list[ServerInboundTrafficDailySeries] = []

    for srv_id, srv_name, srv_host in servers:
        by_user = by_server_user.get(int(srv_id), {})
        if by_user:
            day_delta = _daily_deltas_from_user_series(by_user, grid, start)
            deltas = [int(day_delta.get(d, 0)) for d in dates]
        else:
            deltas = [0 for _ in dates]
        for d, val in zip(dates, deltas, strict=True):
            total_by_day[d] += val
        server_series.append(
            ServerInboundTrafficDailySeries(
                server_id=int(srv_id),
                name=srv_name,
                host=str(srv_host or ""),
                delta_inbound_bytes=deltas,
            ),
        )

    return AllServersInboundTrafficDailySummary(
        dates=dates,
        total_delta_inbound_bytes=[int(total_by_day[d]) for d in dates],
        servers=server_series,
        exit_server_ids=_cascade_exit_server_ids(db),
    )


async def all_servers_inbound_traffic_daily_db_only(
    *,
    days: int = 90,
) -> AllServersInboundTrafficDailySummary:
    return await run_blocking_with_session(_all_servers_inbound_traffic_daily_blocking, days)
