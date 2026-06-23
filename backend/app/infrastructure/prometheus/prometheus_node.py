"""
Загрузка метрик node_exporter из Prometheus (query_range).

Ожидается, что у цели в Prometheus label ``instance`` совпадает с
``servers.prometheus_instance`` (если задано) или с ``{host}:{PROVISION_NODE_EXPORTER_PORT}``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.core.time import utc_now

log = logging.getLogger("app.prometheus")

# Префикс detail при ошибке Prometheus: sync_all_servers пропускает остальные узлы.
PROMETHEUS_BATCH_ABORT_DETAIL_PREFIX = "[prom-batch-abort]"
# Внутри сообщения о cooldown circuit breaker.
PROMETHEUS_COOLDOWN_MARKER = "[prometheus-cooldown]"

_prom_circuit_open_until: float = 0.0


def prometheus_batch_abort_detail(message: str) -> str:
    msg = (message or "").strip()
    if msg.startswith(PROMETHEUS_BATCH_ABORT_DETAIL_PREFIX):
        return msg
    return f"{PROMETHEUS_BATCH_ABORT_DETAIL_PREFIX} {msg}"


def _circuit_is_open() -> bool:
    return time.monotonic() < _prom_circuit_open_until


def _circuit_trip(reason: str) -> None:
    global _prom_circuit_open_until
    cooldown = float(settings.prometheus_circuit_cooldown_seconds)
    _prom_circuit_open_until = time.monotonic() + max(5.0, cooldown)
    log.warning("Prometheus: пауза запросов на %.0f с (%s)", cooldown, reason)


def _circuit_reset() -> None:
    global _prom_circuit_open_until
    _prom_circuit_open_until = 0.0


def _circuit_check() -> None:
    if _circuit_is_open():
        left = int(_prom_circuit_open_until - time.monotonic()) + 1
        raise RuntimeError(
            prometheus_batch_abort_detail(
                f"{PROMETHEUS_COOLDOWN_MARKER} Prometheus недоступен, повтор через ~{left} с"
            )
        )


def _prometheus_http_client(timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        trust_env=bool(settings.prometheus_trust_env),
    )

# PromQL для типичного node_exporter; instance подставляется как экранированная строка.
_QUERIES: dict[str, str] = {
    "cpu_percent": (
        '100 * (1 - avg without (cpu, mode) '
        '(rate(node_cpu_seconds_total{{mode="idle",instance="{i}"}}[2m])))'
    ),
    "memory_percent": (
        '100 * (1 - (node_memory_MemAvailable_bytes{{instance="{i}"}} '
        '/ node_memory_MemTotal_bytes{{instance="{i}"}}))'
    ),
    "memory_used_mb": (
        '(node_memory_MemTotal_bytes{{instance="{i}"}} '
        '- node_memory_MemAvailable_bytes{{instance="{i}"}}) / 1024 / 1024'
    ),
    "memory_total_mb": 'node_memory_MemTotal_bytes{{instance="{i}"}} / 1024 / 1024',
    "load_avg_1m": 'node_load1{{instance="{i}"}}',
    "disk_used_percent": (
        '100 * (1 - node_filesystem_avail_bytes{{instance="{i}",mountpoint="/",fstype!="rootfs"}} '
        '/ node_filesystem_size_bytes{{instance="{i}",mountpoint="/",fstype!="rootfs"}})'
    ),
    "net_rx_mbps": (
        'sum(rate(node_network_receive_bytes_total{{instance="{i}",device!="lo"}}[2m])) * 8 / 1000000'
    ),
    "net_tx_mbps": (
        'sum(rate(node_network_transmit_bytes_total{{instance="{i}",device!="lo"}}[2m])) * 8 / 1000000'
    ),
    "tcp_established": 'node_netstat_Tcp_CurrEstab{{instance="{i}"}}',
    "uptime_seconds": 'time() - node_boot_time_seconds{{instance="{i}"}}',
}

# Textfile collector (vpn-warp-check.sh на узлах с google_routing_mode=entry).
_WARP_INSTANT: dict[str, str] = {
    "profile_ok": 'vpn_warp_profile_ok{{instance="{i}"}}',
    "outbound_ok": 'vpn_warp_outbound_ok{{instance="{i}"}}',
    "endpoint_ok": 'vpn_warp_endpoint_reachable{{instance="{i}"}}',
    "cf_api_ok": 'vpn_warp_cf_api_ok{{instance="{i}"}}',
    "warp_plus": 'vpn_warp_warp_plus{{instance="{i}"}}',
    "probe_ok": 'vpn_warp_probe_ok{{instance="{i}"}}',
    "probe_latency_ms": 'vpn_warp_probe_latency_ms{{instance="{i}"}}',
    "last_check_ts": 'vpn_warp_last_check_timestamp{{instance="{i}"}}',
    "quota_bytes": 'vpn_warp_quota_bytes{{instance="{i}"}}',
    "premium_data_bytes": 'vpn_warp_premium_data_bytes{{instance="{i}"}}',
}


def _escape_instance(i: str) -> str:
    return i.replace("\\", "\\\\").replace('"', '\\"')


def _base_url() -> str:
    return (settings.prometheus_base_url or "").strip().rstrip("/")


def _query_instant_scalar(client: httpx.Client, query: str) -> float | None:
    """Один числовой sample из /api/v1/query (vector/scalar)."""
    r = client.get(
        f"{_base_url()}/api/v1/query",
        params={"query": query},
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        log.warning("Prometheus instant query: %s", payload.get("error") or payload)
        return None
    res = payload.get("data", {}).get("result") or []
    if not res:
        return None
    try:
        return float(res[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fetch_analytics_axis_hints(instance: str) -> dict[str, Any]:
    """
    Instant-запросы к Prometheus: скорость NIC (верх сетевого графика), число CPU.
    """
    base = _base_url()
    if not base:
        return {}
    inst = _escape_instance(instance.strip())
    hints: dict[str, Any] = {}
    try:
        _circuit_check()
        timeout = min(float(settings.prometheus_timeout_seconds), 15.0)
        with _prometheus_http_client(timeout) as client:
            speed = _query_instant_scalar(
                client,
                f'max(node_network_speed_bytes{{instance="{inst}",device!="lo"}})',
            )
            cores = _query_instant_scalar(
                client,
                f'count(node_cpu_seconds_total{{instance="{inst}",mode="idle"}})',
            )
        if speed is not None and speed > 0:
            hints["nic_mbps"] = round(speed * 8 / 1_000_000, 2)
        if cores is not None and cores >= 1:
            hints["cpu_cores"] = int(cores)
    except httpx.HTTPError as e:
        log.warning("Prometheus axis hints HTTP: %s", e)
    except Exception as e:
        log.warning("Prometheus axis hints: %s", e)
    return hints


def format_query_with_instance(template: str, instance: str) -> str:
    """Заменяет в шаблоне PromQL подстроку {instance} на экранированное значение label."""
    inst = _escape_instance(instance.strip())
    t = (template or "").strip()
    if "{instance}" in t:
        return t.replace("{instance}", inst)
    return t


def _query_instant_vector_labels(
    client: httpx.Client,
    query: str,
) -> list[dict[str, str]]:
    r = client.get(f"{_base_url()}/api/v1/query", params={"query": query})
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        return []
    out: list[dict[str, str]] = []
    for item in payload.get("data", {}).get("result") or []:
        metric = item.get("metric")
        if isinstance(metric, dict):
            out.append({str(k): str(v) for k, v in metric.items()})
    return out


def _warp_metric_scalar(instance: str, key: str) -> float | None:
    tpl = _WARP_INSTANT.get(key)
    if not tpl:
        return None
    q = format_query_with_instance(tpl, instance)
    return fetch_instant_scalar(q)


def fetch_warp_status_from_prometheus(instance: str) -> dict[str, Any]:
    """
    Instant-метрики WARP из textfile collector (vpn-warp-check на узле).
    Пустой dict, если метрик нет (мониторинг не установлен или Prometheus не scrape'ит).
    """
    inst = (instance or "").strip()
    if not inst or not _base_url():
        return {}

    def _flag(key: str) -> bool | None:
        v = _warp_metric_scalar(inst, key)
        if v is None:
            return None
        return bool(int(v))

    def _num(key: str) -> float | None:
        return _warp_metric_scalar(inst, key)

    account_type: str | None = None
    license_name: str | None = None
    try:
        _circuit_check()
        timeout = min(float(settings.prometheus_timeout_seconds), 15.0)
        with _prometheus_http_client(timeout) as client:
            q = format_query_with_instance('vpn_warp_info{{instance="{i}"}}', inst)
            labels = _query_instant_vector_labels(client, q)
            if labels:
                account_type = labels[0].get("account_type") or None
                license_name = labels[0].get("license") or None
    except Exception as e:
        log.warning("Prometheus warp_info: %s", e)

    last_ts = _num("last_check_ts")
    quota = _num("quota_bytes")
    used = _num("premium_data_bytes")
    quota_known = quota is not None and quota >= 0
    used_known = used is not None and used >= 0
    quota_remaining: float | None = None
    if quota_known and used_known:
        quota_remaining = max(0.0, quota - used)

    profile_ok = _flag("profile_ok")
    endpoint_ok = _flag("endpoint_ok")
    cf_ok = _flag("cf_api_ok")
    overall: bool | None = None
    if profile_ok is not None or endpoint_ok is not None:
        overall = bool(profile_ok) and bool(endpoint_ok) and bool(cf_ok if cf_ok is not None else True)

    return {
        "monitored": profile_ok is not None or endpoint_ok is not None,
        "overall_ok": overall,
        "profile_ok": profile_ok,
        "outbound_ok": _flag("outbound_ok"),
        "endpoint_ok": endpoint_ok,
        "cf_api_ok": cf_ok,
        "warp_plus": _flag("warp_plus"),
        "youtube_probe_ok": _flag("probe_ok"),
        "probe_latency_ms": _num("probe_latency_ms"),
        "last_check_at": (
            datetime.fromtimestamp(last_ts, tz=timezone.utc) if last_ts is not None else None
        ),
        "account_type": account_type,
        "license": license_name,
        "quota_bytes": quota if quota_known else None,
        "premium_data_bytes": used if used_known else None,
        "quota_remaining_bytes": quota_remaining,
    }


def fetch_instant_scalar(query: str) -> float | None:
    """
    Произвольный PromQL instant query; одно скалярное/векторное значение.
    """
    base = _base_url()
    q = (query or "").strip()
    if not base or not q:
        return None
    try:
        _circuit_check()
        timeout = min(float(settings.prometheus_timeout_seconds), 15.0)
        with _prometheus_http_client(timeout) as client:
            return _query_instant_scalar(client, q)
    except httpx.HTTPError as e:
        log.warning("Prometheus instant (custom) HTTP: %s", e)
    except Exception as e:
        log.warning("Prometheus instant (custom): %s", e)
    return None


def _matrix_to_pairs(result: dict[str, Any]) -> list[tuple[float, float]]:
    res = result.get("data", {}).get("result") or []
    if not res:
        return []
    values = res[0].get("values") or []
    out: list[tuple[float, float]] = []
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        try:
            ts = float(pair[0])
            val = float(pair[1])
        except (TypeError, ValueError):
            continue
        out.append((ts, val))
    return out


def _query_range(
    client: httpx.Client,
    query: str,
    start: float,
    end: float,
    step: int,
) -> list[tuple[float, float]]:
    """502/503: при prometheus_range_retries>1 — короткий backoff (TSDB / краткий сбой)."""
    max_attempts = max(1, int(settings.prometheus_range_retries))
    backoff_s = 0.4
    last: httpx.Response | None = None
    for attempt in range(max_attempts):
        try:
            last = client.get(
                f"{_base_url()}/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(start),
                    "end": str(end),
                    "step": str(step),
                },
            )
        except httpx.RequestError as e:
            if attempt + 1 < max_attempts:
                time.sleep(backoff_s * (attempt + 1))
                continue
            _circuit_trip(str(e))
            raise
        if last.status_code in (502, 503) and attempt + 1 < max_attempts:
            time.sleep(backoff_s * (attempt + 1))
            continue
        if last.status_code in (502, 503):
            _circuit_trip(f"HTTP {last.status_code}")
        try:
            last.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        payload = last.json()
        if payload.get("status") != "success":
            log.warning("Prometheus query_range не success: %s", payload.get("error") or payload)
            return []
        pairs = _matrix_to_pairs(payload)
        _circuit_reset()
        return pairs
    return []


def _forward_fill(t: float, pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    last: float | None = None
    for ts, v in pairs:
        if ts <= t:
            last = v
        else:
            break
    return last


def fetch_node_metrics_merged(
    instance: str,
    *,
    hours: int,
    step_seconds: int,
) -> tuple[list[dict[str, Any]], int]:
    """
    Возвращает (список точек для API, выбранный step).
    Каждая точка: recorded_at (iso), метрики или None.
    """
    base = _base_url()
    if not base:
        raise RuntimeError("PROMETHEUS_BASE_URL не задан")

    _circuit_check()

    inst = _escape_instance(instance.strip())
    end = utc_now().timestamp()
    start = end - hours * 3600
    step = max(15, min(300, step_seconds))

    series: dict[str, list[tuple[float, float]]] = {}
    timeout = settings.prometheus_timeout_seconds
    prom_failed = False
    with _prometheus_http_client(timeout) as client:
        for name, tmpl in _QUERIES.items():
            if prom_failed:
                series[name] = []
                continue
            q = tmpl.format(i=inst)
            try:
                series[name] = _query_range(client, q, start, end, step)
            except httpx.HTTPError as e:
                log.warning(
                    "Prometheus запрос %s: %s — дальнейшие query_range для этого узла пропущены",
                    name,
                    e,
                )
                series[name] = []
                prom_failed = True

    times: set[int] = set()
    for pairs in series.values():
        for ts, _ in pairs:
            times.add(int(ts))

    if not times:
        t0 = int(start)
        t1 = int(end)
        t = t0
        n = 0
        while t <= t1 and n < 3000:
            times.add(t)
            t += step
            n += 1

    sorted_ts = sorted(times)
    points: list[dict[str, Any]] = []
    for t in sorted_ts:
        t_f = float(t)
        cpu = _forward_fill(t_f, series.get("cpu_percent") or [])
        mem_pct = _forward_fill(t_f, series.get("memory_percent") or [])
        mem_u = _forward_fill(t_f, series.get("memory_used_mb") or [])
        mem_tot = _forward_fill(t_f, series.get("memory_total_mb") or [])
        load1 = _forward_fill(t_f, series.get("load_avg_1m") or [])
        disk = _forward_fill(t_f, series.get("disk_used_percent") or [])
        rx = _forward_fill(t_f, series.get("net_rx_mbps") or [])
        tx = _forward_fill(t_f, series.get("net_tx_mbps") or [])
        tcp = _forward_fill(t_f, series.get("tcp_established") or [])
        up = _forward_fill(t_f, series.get("uptime_seconds") or [])

        points.append(
            {
                "recorded_at": datetime.fromtimestamp(t_f, tz=timezone.utc),
                "cpu_percent": cpu,
                "memory_percent": mem_pct,
                "memory_used_mb": mem_u,
                "memory_total_mb": mem_tot,
                "load_avg_1m": load1,
                "disk_used_percent": disk,
                "net_rx_mbps": rx,
                "net_tx_mbps": tx,
                "tcp_established": int(tcp) if tcp is not None else None,
                "uptime_seconds": int(up) if up is not None else None,
            }
        )

    return points, step
