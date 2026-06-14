"""Pydantic-модели журнала баланса пользователя."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UserBalanceLedgerItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_rub: Decimal = Field(description="Сумма операции в рублях (+ зачисление)")
    kind: str
    referee_id: int | None = None
    referee_payment_id: int | None = None
    task_id: int | None = None
    note: str | None = None
    created_at: datetime


class UserBalanceLedgerListResponse(BaseModel):
    items: list[UserBalanceLedgerItem]
    total: int = Field(ge=0)
