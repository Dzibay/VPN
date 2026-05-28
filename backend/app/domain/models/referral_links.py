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


class ReferralDirectTrafficStats(BaseModel):
    """Пользователи без привязки к реферальной ссылке (прямой трафик)."""

    total: int = Field(
        ge=0,
        description="Все пользователи с referral_link_id IS NULL",
    )
    with_telegram_id: int = Field(
        ge=0,
        description="Прямой трафик с telegram_id (регистрация через Telegram без ref/start)",
    )
    without_telegram_id: int = Field(
        ge=0,
        description="Прямой трафик без telegram_id (регистрация на сайте без ?ref)",
    )


class ReferralFunnelSummary(BaseModel):
    """Воронка: без фильтра — пользователи БД и трафик; при выборе ссылки — клики по счётчику и дальше."""

    registrations_total: int = Field(
        ge=0,
        description=(
            "Без фильтра — число всех пользователей в БД; при referral_link_id — счётчик регистраций по этой ссылке"
        ),
    )
    users_with_traffic: int = Field(
        ge=0,
        description=(
            "Пользователей с ненулевым трафиком по узлам: вся БД или только с выбранным referral_link_id"
        ),
    )
    users_with_subscription_device: int = Field(
        ge=0,
        description=(
            "Пользователей с хотя бы одной записью subscription_devices (подключённое устройство по подписке)"
        ),
    )
    active_users_today_utc: int = Field(
        ge=0,
        description=(
            "Активные за текущий календарный день UTC: накопленный трафик вырос относительно предыдущего дня "
            "(та же логика, что active_users_count в GET /api/users/daily-stats)"
        ),
    )
    clicks_total: int | None = Field(
        default=None,
        description="Только при referral_link_id: накопительный счётчик кликов по этой ссылке",
    )


class ReferralLinkOut(ReferralLinkRead):
    """Ответ админ-API: те же поля + готовые ссылки (SITE_ADDRESS на API, TELEGRAM_BOT_USERNAME)."""

    site_entry_url: str | None = Field(
        default=None,
        description="Главная страница сайта: /?ref={token}",
    )
    telegram_deep_link: str | None = Field(
        default=None,
        description="https://t.me/{TELEGRAM_BOT_USERNAME}?start={token}",
    )


class ReferralMeResponse(BaseModel):
    """GET /api/referral/me: персональная ссылка текущей учётной записи (при отсутствии создаётся автоматически)."""

    link: ReferralLinkOut = Field(
        description="Текущая персональная ссылка; при первом успешном запросе создаётся на сервере",
    )
    bonus_days_pending_activation: int = Field(
        ge=0,
        description=(
            "Бонусные дни реферера, ожидающие активации: сумма bonus_days задач notify_ref_pay "
            "после created_at последней notify_payment этого пользователя (см. app.domain.referrals.task_bonus_days)"
        ),
    )
    bonus_days_received: int = Field(
        ge=0,
        description=(
            "Уже полученные бонусные дни: сумма bonus_days по всем notify_payment этого пользователя"
        ),
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
