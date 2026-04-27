from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SubscriptionOpenClientItem(BaseModel):
    """Элемент списка клиентов для кнопок «Подключить» в личном кабинете."""

    slug: str = Field(description="Идентификатор в URL /sub/{token}/open/{slug}")
    display_name: str = Field(description="Подпись на кнопке")


class AccountRegisterBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72, description="До 72 байт (ограничение bcrypt)")


class AccountLoginBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)


class TelegramAuthBody(BaseModel):
    """Вход/регистрация по Telegram: только вызов с доверенного бэкенда бота (секрет в заголовке)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "telegram_id": 123456789,
                    "username": "ivan_dev",
                    "first_name": "Иван",
                    "last_name": "Петров",
                    "topic_id": 2,
                }
            ]
        },
    )

    telegram_id: int = Field(
        ge=1,
        le=9223372036854775807,
        description="Числовой id пользователя в Telegram (как в Bot API).",
    )
    username: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Ник в Telegram (без @); сохраняется в users.telegram_properties.username."
        ),
    )
    first_name: str | None = Field(
        default=None,
        max_length=255,
        description="Имя; в users.telegram_properties.first_name.",
    )
    last_name: str | None = Field(
        default=None,
        max_length=255,
        description="Фамилия; в users.telegram_properties.last_name.",
    )
    topic_id: int | None = Field(
        default=None,
        ge=1,
        le=9223372036854775807,
        description="Id топика; в users.telegram_properties.topic_id.",
    )


def merge_telegram_auth_profile(
    body: "TelegramAuthBody",
    existing: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Собирает telegram_properties из полей запроса; пустые строки отбрасываются."""
    string_keys = ("username", "first_name", "last_name")
    out: dict[str, Any] = dict(existing) if existing else {}
    for key in string_keys:
        if key not in body.model_fields_set:
            continue
        val = getattr(body, key)
        if val is None:
            out.pop(key, None)
        else:
            s = str(val).strip()
            if s:
                out[key] = s
            else:
                out.pop(key, None)
    if "topic_id" in body.model_fields_set:
        tid = body.topic_id
        if tid is None:
            out.pop("topic_id", None)
        else:
            out["topic_id"] = int(tid)
    return out if out else None


def telegram_auth_has_profile_fields(body: "TelegramAuthBody") -> bool:
    return bool(
        {"username", "first_name", "last_name", "topic_id"} & set(body.model_fields_set),
    )


class AccountMeResponse(BaseModel):
    """Схема ответа GET /api/auth/me; в Swagger смотрите примеры у этой операции."""

    role: str = Field(description="`user` | `admin`")
    id: int | None = Field(
        default=None,
        description="Внутренний id в БД; у admin всегда null.",
    )
    email: str | None = Field(
        default=None,
        description="Email из БД; `null`, если регистрация только через Telegram.",
    )
    telegram_id: int | None = Field(
        default=None,
        description="Числовой id Telegram; `null`, если не привязан.",
    )
    telegram_properties: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Словарь из `username`, `first_name`, `last_name`, `topic_id` (и др.) "
            "из `/api/auth/telegram`; для `admin` — `null`."
        ),
    )
    subscription_until: date | None = Field(
        default=None,
        description="Включительно; `null` — без срока или не задано.",
    )
    subscription_active: bool = Field(
        default=False,
        description="True, если срок подписки ещё действует.",
    )
    subscription_token: str = Field(
        default="",
        description=(
            "Токен для публичных URL `/sub/{token}` и `/sub/{token}/json` "
            "(не JWT); у admin пустая строка."
        ),
    )
    subscription_open_clients: list[SubscriptionOpenClientItem] = Field(
        default_factory=list,
        description="Клиенты VPN для кнопок подключения в ЛК; у admin — пустой список.",
    )
