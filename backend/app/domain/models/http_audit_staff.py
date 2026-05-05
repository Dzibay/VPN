"""Схемы ответов для журнала HTTP-запросов (staff / admin)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HttpRequestTraceStaffItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    user_id: int | None
    subject_source: str
    http_method: str
    path: str
    status_code: int
    duration_ms: float = Field(description="Длительность запроса, мс")
    client_ip: str
    created_at: datetime


class HttpRequestTraceStaffPage(BaseModel):
    items: list[HttpRequestTraceStaffItem]
    total: int
    limit: int
    offset: int
