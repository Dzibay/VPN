from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UsersCountResponse(BaseModel):
    users_count: int = Field(ge=0, description="Число записей в таблице users")


class UserCreate(BaseModel):
    telegram_id: str | None = Field(
        default=None,
        max_length=128,
        description="Логин Telegram; пусто — не указывать",
    )
    subscription_until: date | None = Field(
        default=None,
        description="Дата окончания подписки (календарный день). Пусто — без срока",
    )

    @field_validator("telegram_id", mode="before")
    @classmethod
    def normalize_telegram_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("subscription_until", mode="before")
    @classmethod
    def coerce_subscription_until(cls, v: object) -> date | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            return date.fromisoformat(s[:10])
        raise ValueError("subscription_until: ожидается дата (YYYY-MM-DD)")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: str | None
    subscription_until: date | None
    token: str = Field(description="Токен для ссылки подписки /sub/{token}")


class SubscriptionPayload(BaseModel):
    """Ответ по токену подписки (список серверов — позже)."""

    valid_until: date | None = Field(
        description="Подписка действительна до (включительно, календарная дата), null — без ограничения",
    )
    servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Список узлов VPN (заглушка до появления конфигурации серверов)",
    )
