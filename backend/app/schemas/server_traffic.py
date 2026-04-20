from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServerUserTrafficRow(BaseModel):
    user_id: int
    telegram_id: str | None = None
    up_bytes: int = Field(ge=0)
    down_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0, description="up + down (накоплено в БД)")


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


class UserTrafficCollectEnqueueResponse(BaseModel):
    server_id: int
    job_id: str = Field(description="RQ job id — опрос GET .../collect-jobs/{job_id}")


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
