from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NotificationTaskType = Literal["notify_reg", "notify_payment"]


class TelegramNotificationTaskItem(BaseModel):
    """Одна невыполненная задача оповещения (бот рассылает user_id / referee_id)."""

    id: int
    type: NotificationTaskType
    user_id: int
    referee_id: int | None = None
    bonus_days: int | None = None
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
    """Идентификаторы задач, которые бот успешно обработал (проставится done_at)."""

    task_ids: list[int] = Field(default_factory=list, max_length=500)

    @field_validator("task_ids")
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
        description="Строки, у которых реально выставлен done_at (ожидали pending и тип оповещения).",
    )
