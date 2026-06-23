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


class ServerWarpStatusRead(BaseModel):
    """Состояние Cloudflare WARP на узле (Prometheus textfile collector)."""

    enabled: bool = Field(
        description="True, если у сервера google_routing_mode=entry (WARP задуман на узле)",
    )
    monitored: bool = Field(
        False,
        description="True, если метрики vpn_warp_* видны в Prometheus",
    )
    prometheus_instance: str = Field(description="label instance в Prometheus")
    overall_ok: bool | None = Field(
        None,
        description="Сводная оценка: профиль + endpoint + CF API",
    )
    profile_ok: bool | None = None
    outbound_ok: bool | None = None
    account_ok: bool | None = Field(
        None,
        description="wgcf-account.toml присутствует на узле",
    )
    endpoint_ok: bool | None = None
    cf_api_ok: bool | None = None
    warp_plus: bool | None = None
    youtube_probe_ok: bool | None = Field(
        None,
        description="Доступность YouTube generate_204 с самого сервера (не через Xray/WARP)",
    )
    probe_latency_ms: float | None = None
    last_check_at: datetime | None = None
    account_type: str | None = Field(
        None,
        description="Тип аккаунта из Cloudflare WARP API (free / unlimited / …)",
    )
    license: str | None = None
    quota_bytes: int | None = Field(
        None,
        description="Лимит premium-трафика WARP из CF API, если отдаётся",
    )
    premium_data_bytes: int | None = Field(
        None,
        description="Использовано premium-трафика WARP, если отдаётся API",
    )
    quota_remaining_bytes: int | None = Field(
        None,
        description="Остаток quota − used, если оба известны",
    )
    last_error: str | None = Field(
        None,
        description="Последняя ошибка CF API из vpn_warp_last_error",
    )
    detail: str = Field(
        default="",
        description="Краткое пояснение для админки",
    )
