from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServerMetricPoint(BaseModel):
    """Одна временная точка (node_exporter через Prometheus)."""

    recorded_at: datetime
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    load_avg_1m: float | None = None
    tcp_established: int | None = None
    net_rx_mbps: float | None = None
    net_tx_mbps: float | None = None
    disk_used_percent: float | None = None
    uptime_seconds: int | None = None


class ServerMetricsFromPrometheus(BaseModel):
    source: Literal["prometheus"] = "prometheus"
    instance: str = Field(description="Значение label instance в Prometheus")
    step_seconds: int
    points: list[ServerMetricPoint]
