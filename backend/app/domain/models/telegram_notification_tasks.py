from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NotificationTaskType = Literal[
    "notify_ref_reg",
    "notify_ref_pay",
    "notify_payment",
    "notify_sub_expire_3d",
    "notify_sub_expire_1d",
    "notify_sub_expire_0d",
    "notify_sub_expire",
    "notify_sub_expired_7d",
]


class TelegramNotificationTaskItem(BaseModel):
    """Одна невыполненная задача оповещения (бот рассылает user_id / referee_id)."""

    id: int
    type: NotificationTaskType
    user_id: int
    referee_id: int | None = None
    bonus_days: int | None = None
    paid_months: int | None = Field(
        default=None,
        ge=1,
        description="Для type=notify_payment: оплаченные месяцы (как payments.months).",
    )
    created_at: datetime
    recipient_telegram_id: int | None = Field(
        default=None,
        description="users.telegram_id для user_id (кому писать), если привязан.",
    )
    referee_telegram_id: int | None = Field(
        default=None,
        description="users.telegram_id для referee_id, если есть и привязан.",
    )


class TelegramNotificationTasksListResponse(BaseModel):
    tasks: list[TelegramNotificationTaskItem]


class TelegramTasksAckBody(BaseModel):
    """Идентификаторы задач, которые бот обработал, разделённые по исходу."""

    completed_task_ids: list[int] = Field(default_factory=list, max_length=500)
    failed_task_ids: list[int] = Field(default_factory=list, max_length=500)

    @field_validator("completed_task_ids", "failed_task_ids")
    @classmethod
    def positive_unique(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for x in v:
            if x < 1:
                raise ValueError("Каждый task_id должен быть >= 1")
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out


class TelegramTasksAckResponse(BaseModel):
    completed_task_ids: list[int] = Field(
        description="Строки, которым реально выставлен статус completed (ожидали pending и тип оповещения).",
    )
    failed_task_ids: list[int] = Field(
        description="Строки, которым реально выставлен статус failed (ожидали pending и тип оповещения).",
    )
