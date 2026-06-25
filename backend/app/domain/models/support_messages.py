from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Сообщение не может быть пустым")
        return trimmed


class SupportMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(ge=1)
    author_kind: Literal["user", "staff"]
    body: str
    created_at: datetime


class SupportMessagesListResponse(BaseModel):
    items: list[SupportMessageRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class StaffSupportMessageRead(SupportMessageRead):
    staff_user_id: int | None = Field(
        default=None,
        description="ID staff, отправившего ответ (только author_kind=staff)",
    )
    staff_author_label: str | None = Field(
        default=None,
        description="Подпись автора ответа; заполняется только для admin в staff API",
    )


class StaffSupportMessagesListResponse(BaseModel):
    items: list[StaffSupportMessageRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class StaffSupportChatSummary(BaseModel):
    user_id: int = Field(ge=1)
    user_label: str
    user_email: str | None = None
    telegram_username: str | None = None
    last_message_id: int = Field(ge=1)
    last_message_body: str
    last_message_at: datetime
    last_author_kind: Literal["user", "staff"]
    needs_reply: bool
    messages_count: int = Field(ge=1)


class StaffSupportChatsListResponse(BaseModel):
    items: list[StaffSupportChatSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    needs_reply_count: int = Field(ge=0)


class StaffSupportBadgeResponse(BaseModel):
    needs_reply_count: int = Field(ge=0, description="Чаты, где последнее сообщение от пользователя")


class SupportUnreadCountResponse(BaseModel):
    unread_count: int = Field(ge=0)
