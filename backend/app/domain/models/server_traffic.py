from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServerUserTrafficRow(BaseModel):
    user_id: int
    telegram_id: int | None = None
    up_bytes: int = Field(ge=0)
    down_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0, description="up + down (накоплено в БД)")
    delta_total_bytes: int = Field(
        default=0,
        ge=0,
        description=(
            "Только если последняя по дате строка user_server_traffic на этом узле "
            "имеет traffic_date = сегодня (UTC): (up+down) этой строки минус (up+down) "
            "последней строки с датой строго раньше сегодня; иначе 0; не ниже 0"
        ),
    )


class UserTrafficCollectDetail(BaseModel):
    """Что сделал бэкенд при опросе узла (SSH + xray api statsquery)."""

    ssh_target: str | None = Field(
        default=None,
        description="user@host, как в SSH",
    )
    ssh_port: int | None = None
    xray_api_listen: str | None = Field(
        default=None,
        description="Адрес Stats API на узле, например 127.0.0.1:10085",
    )
    remote_command: str | None = Field(
        default=None,
        description="Удалённая команда (внутри bash -lc)",
    )
    exit_code: int | None = None
    duration_ms: float | None = None
    stdout_preview: str | None = None
    stderr_preview: str | None = None
    parsed_users: int | None = Field(
        default=None,
        description="Сколько пользователей распознано в JSON ответа",
    )
    skipped_reason: str | None = Field(
        default=None,
        description="Если SSH не выполнялся (ранний выход)",
    )


class ServerUserTrafficBundle(BaseModel):
    server_id: int
    collected_at: datetime | None = Field(
        default=None,
        description="Время успешного опроса Xray (UTC)",
    )
    collect_error: str | None = Field(
        default=None,
        description="Текст ошибки SSH/statsquery; данные могут быть из прошлого сбора",
    )
    collect_detail: UserTrafficCollectDetail | None = Field(
        default=None,
        description="Детали последнего collect=true (SSH, фрагменты вывода)",
    )
    users: list[ServerUserTrafficRow] = Field(default_factory=list)


class ServerTrafficDailyPoint(BaseModel):
    """Один календарный день UTC по узлу: накопленная сумма суточных приростов и прирост за день."""

    traffic_date: date
    total_sum_bytes: int = Field(
        ge=0,
        description=(
            "Накопительно с начала окна: сумма по всем пользователям суточных дельт "
            "(каждая дельта — max(0, снимок на конец дня минус снимок на конец предыдущего дня), "
            "снимок переносится между днями без строки в БД)"
        ),
    )
    delta_sum_bytes: int = Field(
        ge=0,
        description=(
            "За этот календарный день UTC: сумма по пользователям max(0, T_i(D)−T_i(D−1)), "
            "где T_i(D) — последний известный (up+down) пользователя i на узле с traffic_date ≤ D"
        ),
    )


class ServerTrafficDailySummary(BaseModel):
    server_id: int
    points: list[ServerTrafficDailyPoint] = Field(default_factory=list)


class ServerInboundTrafficDailySeries(BaseModel):
    """Суточный прирост входящего трафика (down_bytes) по одному узлу."""

    server_id: int
    name: str | None = None
    host: str
    delta_inbound_bytes: list[int] = Field(
        default_factory=list,
        description="По дням dates: суточный прирост down_bytes (не накопительно)",
    )


class AllServersInboundTrafficDailySummary(BaseModel):
    """Суточный входящий трафик по всем узлам: сумма и отдельные линии."""

    dates: list[date] = Field(default_factory=list)
    total_delta_inbound_bytes: list[int] = Field(
        default_factory=list,
        description="Сумма delta_inbound_bytes по всем узлам за каждый день",
    )
    servers: list[ServerInboundTrafficDailySeries] = Field(default_factory=list)


class UserTrafficCollectEnqueueResponse(BaseModel):
    server_id: int
    job_id: str = Field(description="RQ job id — опрос GET .../collect-jobs/{job_id}")


class UserTrafficCollectAllEnqueueResponse(BaseModel):
    job_id: str = Field(
        description="RQ job id батч-сбора по активным provision_ready узлам",
    )


class UserTrafficCollectPollResponse(BaseModel):
    server_id: int
    job_id: str
    status: Literal["queued", "started", "finished", "failed"]
    bundle: ServerUserTrafficBundle | None = Field(
        default=None,
        description="Заполнен при status=finished (результат сбора + строки из БД)",
    )
    job_error: str | None = Field(
        default=None,
        description="Текст при падении задачи RQ (исключение воркера)",
    )


class UserTrafficPerServerRow(BaseModel):
    """Трафик одного пользователя на одном узле + краткие поля сервера."""

    server_id: int
    name: str | None = None
    host: str
    port: int
    country: str = ""
    is_active: bool = True
    provision_ready: bool = False
    up_bytes: int = Field(ge=0)
    down_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0, description="up + down (накоплено в БД)")


class UserTrafficByServersBundle(BaseModel):
    """Сводка по пользователю: все узлы из БД и трафик (LEFT JOIN, без трафика — нули)."""

    user_id: int
    telegram_id: int | None = None
    subscription_until: date | None = None
    servers: list[UserTrafficPerServerRow] = Field(default_factory=list)
    total_up_bytes: int = Field(ge=0)
    total_down_bytes: int = Field(ge=0)


class UserTrafficByDayRow(BaseModel):
    """Накопительная сумма up+down по всем узлам на конец календарного дня UTC."""

    traffic_date: date
    cumulative_bytes: int = Field(
        ge=0,
        description=(
            "Сумма накопленных счётчиков Xray по узлам: для каждого узла берётся последний "
            "снимок с traffic_date ≤ этого дня, затем сумма по узлам"
        ),
    )
