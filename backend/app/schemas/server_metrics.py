from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServerMetricsAxisHints(BaseModel):
    """Подсказки для осей графиков (частично из node_exporter через instant query)."""

    network_max_mbps: float | None = Field(
        None,
        description="Верхняя граница графика сети: тариф (network_cap_mbps) если задан, иначе скорость NIC",
    )
    network_tariff_mbps: int | None = Field(
        None,
        description="Тарифный потолок из БД (Мбит/с)",
    )
    network_nic_mbps: float | None = Field(
        None,
        description="Скорость порта из node_network_speed_bytes (Мбит/с)",
    )
    cpu_cores: int | None = Field(
        None,
        description="Число логических CPU (count node_cpu_seconds_total mode=idle)",
    )
    load_y_max: float | None = Field(
        None,
        description="Рекомендуемый max оси load1 (ядра × 1.2 и запас от данных)",
    )
    tcp_y_max: float | None = Field(
        None,
        description="Рекомендуемый max оси TCP (от пикового значения в ряду)",
    )


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
    net_util_percent: float | None = Field(
        None,
        description="Загрузка канала относительно лимита (тариф или NIC): max(rx,tx)/cap×100, не выше 100",
    )
    load_util_percent: float | None = Field(
        None,
        description="Load1 относительно числа CPU: min(100, load1/cores×100)",
    )
    bottleneck_percent: float | None = Field(
        None,
        description=(
            "Оценка «сколько выдержит сервер»: max из доступных CPU%, RAM%, диск%, сеть%, load% "
            "(узкое место определяет общую утилизацию)"
        ),
    )


class ServerMetricsFromPrometheus(BaseModel):
    source: Literal["prometheus"] = "prometheus"
    instance: str = Field(description="Значение label instance в Prometheus")
    step_seconds: int
    axis: ServerMetricsAxisHints | None = Field(
        None,
        description="Лимиты осей и справка из Prometheus",
    )
    online_clients: int | None = Field(
        None,
        description="Число онлайн-клиентов из prometheus_online_clients_query (instant), если задано",
    )
    online_clients_from_prometheus: bool = Field(
        False,
        description="True, если в настройках задан запрос онлайн-клиентов",
    )
    points: list[ServerMetricPoint]
