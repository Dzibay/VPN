import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Произвольная метка источника (github, bot1, campaign…); зарезервировано «user»
OWNER_KIND_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ReferralLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    owner_kind: str
    owner_user_id: int | None = None
    clicks_count: int = Field(ge=0)
    registrations_count: int = Field(ge=0)
    payments_count: int = Field(ge=0)
    created_at: datetime


class ReferralLinkOut(ReferralLinkRead):
    """Ответ админ-API: те же поля + готовые ссылки (если заданы REFERRAL_SITE_BASE_URL / TELEGRAM_BOT_USERNAME)."""

    site_entry_url: str | None = Field(
        default=None,
        description="Главная страница сайта: /?ref={token}",
    )
    telegram_deep_link: str | None = Field(
        default=None,
        description="Открытие бота в Telegram с параметром start",
    )


class ReferralTrackClickBody(BaseModel):
    """Учёт клика по реферальной ссылке на сайте (публичный POST)."""

    token: str = Field(min_length=1, max_length=64)

    @field_validator("token", mode="before")
    @classmethod
    def strip_token_click(cls, v: object) -> str:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("token не может быть пустым")
            return s
        raise ValueError("token: ожидается строка")


class ReferralLinkCreate(BaseModel):
    """Создание токена; при пустом token генерируется сервером."""

    owner_kind: str = Field(
        min_length=1,
        max_length=64,
        description="Источник: произвольная метка (github, bot1) или «user» с owner_user_id",
    )
    owner_user_id: int | None = Field(
        default=None,
        description="Обязателен при owner_kind=user (в т.ч. синтетический пользователь-бот)",
    )
    token: str | None = Field(
        default=None,
        min_length=4,
        max_length=64,
        description="Latin letters, digits, underscore — как в Telegram ?start= (до 64 символов)",
    )

    @field_validator("owner_kind", mode="before")
    @classmethod
    def strip_owner_kind(cls, v: object) -> str:
        if v is None:
            raise ValueError("owner_kind обязателен")
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("owner_kind не может быть пустым")
            return s
        return str(v)

    @field_validator("owner_kind")
    @classmethod
    def validate_owner_kind_shape(cls, v: str) -> str:
        if not OWNER_KIND_PATTERN.fullmatch(v):
            raise ValueError(
                "owner_kind: допустимы латиница, цифры, подчёркивание и дефис, длина 1–64",
            )
        return v

    @field_validator("token", mode="before")
    @classmethod
    def strip_token(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v


class ReferralLinkUpdate(BaseModel):
    """Правка токена и источника; те же правила, что при создании, token всегда задаётся явно."""

    owner_kind: str = Field(
        min_length=1,
        max_length=64,
        description="Источник или «user» с owner_user_id",
    )
    owner_user_id: int | None = Field(
        default=None,
        description="Обязателен при owner_kind=user",
    )
    token: str = Field(
        min_length=4,
        max_length=64,
        description="Latin letters, digits, underscore (Telegram start)",
    )

    @field_validator("owner_kind", mode="before")
    @classmethod
    def strip_owner_kind_upd(cls, v: object) -> str:
        if v is None:
            raise ValueError("owner_kind обязателен")
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("owner_kind не может быть пустым")
            return s
        return str(v)

    @field_validator("owner_kind")
    @classmethod
    def validate_owner_kind_shape_upd(cls, v: str) -> str:
        if not OWNER_KIND_PATTERN.fullmatch(v):
            raise ValueError(
                "owner_kind: допустимы латиница, цифры, подчёркивание и дефис, длина 1–64",
            )
        return v

    @field_validator("token", mode="before")
    @classmethod
    def strip_token_upd(cls, v: object) -> str:
        if v is None:
            raise ValueError("token обязателен")
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("token не может быть пустым")
            return s
        return str(v)
