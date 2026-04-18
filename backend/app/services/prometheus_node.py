"""
Загрузка метрик node_exporter из Prometheus (query_range).

Ожидается, что у цели в Prometheus label ``instance`` совпадает с
``servers.prometheus_instance`` (если задано) или с ``{host}:{PROVISION_NODE_EXPORTER_PORT}``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger("app.prometheus")

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
        timeout = min(float(settings.prometheus_timeout_seconds), 15.0)
        with httpx.Client(timeout=timeout) as client:
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


def fetch_instant_scalar(query: str) -> float | None:
    """
    Произвольный PromQL instant query; одно скалярное/векторное значение.
    """
    base = _base_url()
    q = (query or "").strip()
    if not base or not q:
        return None
    try:
        timeout = min(float(settings.prometheus_timeout_seconds), 15.0)
        with httpx.Client(timeout=timeout) as client:
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
    r = client.get(
        f"{_base_url()}/api/v1/query_range",
        params={
            "query": query,
            "start": str(start),
            "end": str(end),
            "step": str(step),
        },
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        log.warning("Prometheus query_range не success: %s", payload.get("error") or payload)
        return []
    return _matrix_to_pairs(payload)


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

    inst = _escape_instance(instance.strip())
    end = datetime.now(timezone.utc).timestamp()
    start = end - hours * 3600
    step = max(15, min(300, step_seconds))

    series: dict[str, list[tuple[float, float]]] = {}
    timeout = settings.prometheus_timeout_seconds
    with httpx.Client(timeout=timeout) as client:
        for name, tmpl in _QUERIES.items():
            q = tmpl.format(i=inst)
            try:
                series[name] = _query_range(client, q, start, end, step)
            except httpx.HTTPError as e:
                log.warning("Prometheus запрос %s: %s", name, e)
                series[name] = []

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
