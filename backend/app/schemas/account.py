from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator


class AccountRegisterBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72, description="До 72 байт (ограничение bcrypt)")


class AccountLoginBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)


class TelegramAuthBody(BaseModel):
    """Вход/регистрация по Telegram: только вызов с доверенного бэкенда бота (секрет в заголовке)."""

    telegram_id: str = Field(
        min_length=1,
        max_length=128,
        description="Идентификатор пользователя в Telegram (строка, как в Bot API).",
    )

    @field_validator("telegram_id", mode="before")
    @classmethod
    def strip_telegram_id(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("telegram_id не может быть пустым")
        return s


class AccountMeResponse(BaseModel):
    role: str = Field(description="user | admin")
    id: int | None = Field(default=None, description="Для admin не заполняется")
    email: str | None = Field(
        default=None,
        description="Email из БД; пусто, если регистрация только через Telegram.",
    )
    telegram_id: str | None = None
    subscription_until: date | None = None
    subscription_active: bool = False
    subscription_token: str = Field(
        default="",
        description="Токен для /sub/{token} (Base64) и /sub/{token}/json; для admin пусто",
    )
