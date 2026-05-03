"""
Расчёт bottleneck_percent / net_util / load_util для точек node_exporter (как на графике).
"""

from __future__ import annotations

from typing import Any


def enrich_bottleneck_metrics(
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
