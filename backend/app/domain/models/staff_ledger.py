"""Списочные ответы админки: платежи и задачи (JWT admin или manager)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class StaffPaymentItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    amount: Decimal
    months: int
    provider: str
    external_id: str | None = None
    created_at: datetime


class StaffPaymentsListResponse(BaseModel):
    items: list[StaffPaymentItem] = Field(description="Строки payments, новые первыми")
    total: int = Field(ge=0, description="Число строк в таблице payments")
    limit: int
    offset: int


class StaffTaskItem(BaseModel):
    id: int
    type: str = Field(description="Значение колонки tasks.type")
    user_id: int
    referee_id: int | None = None
    bonus_days: int | None = None
    paid_months: int | None = None
    status: str
    created_at: datetime
    done_at: datetime | None = None


class StaffTasksListResponse(BaseModel):
    items: list[StaffTaskItem] = Field(description="Строки tasks, новые первыми")
    total: int = Field(ge=0, description="Число строк в таблице tasks")
    limit: int
    offset: int
