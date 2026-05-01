from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UsersCountResponse(BaseModel):
    users_count: int = Field(ge=0, description="Число записей в таблице users")


class UserRegistrationByDateRow(BaseModel):
    """Число пользователей с датой регистрации (календарный день UTC)."""

    registration_date: date | None = Field(
        description="Дата из registered_at в UTC; null — записи без даты регистрации",
    )
    users_count: int = Field(ge=0)
    users_with_traffic_count: int = Field(
        ge=0,
        description=(
            "Сколько из них имеют ненулевой суммарный трафик (up+down по последнему "
            "снимку на каждый узел, таблица user_server_traffic)"
        ),
    )


class UserTrafficActiveByDayRow(BaseModel):
    """Сколько учётных записей «активны» в этот день по росту накопленного трафика."""

    traffic_date: date = Field(description="Календарный день UTC (поле traffic_date)")
    active_users_count: int = Field(
        ge=0,
        description=(
            "Пользователи, у которых сумма up+down по всем узлам (последний снимок на "
            "узел с датой ≤ этот день) стала больше, чем на предыдущий календарный день "
            "(включая появление первых снимков)"
        ),
    )


class UsersDailyStatsResponse(BaseModel):
    """Сводная дневная статистика: регистрации и активность по трафику (UTC)."""

    registrations_by_date: list[UserRegistrationByDateRow] = Field(
        description="Регистрации и доля с трафиком по дню registered_at (UTC)",
    )
    traffic_active_by_day: list[UserTrafficActiveByDayRow] = Field(
        description=(
            "Число пользователей с ростом накопленного трафика по календарным дням "
            "из user_server_traffic"
        ),
    )


class ExtendActiveSubscriptionsBody(BaseModel):
    days: int = Field(
        ge=1,
        le=3650,
        description="Сколько календарных дней прибавить к subscription_until",
    )


class ExtendActiveSubscriptionsResponse(BaseModel):
    updated_count: int = Field(
        ge=0,
        description="Число обновлённых пользователей (только с конечной активной подпиской)",
    )


class UserCreate(BaseModel):
    telegram_id: int | None = Field(
        default=None,
        ge=1,
        le=9223372036854775807,
        description="Числовой id пользователя в Telegram; пусто — не указывать",
    )
    telegram_properties: dict[str, Any] | None = Field(
        default=None,
        description="Доп. поля (username, …); пусто — не указывать",
    )
    subscription_until: date | None = Field(
        default=None,
        description="Дата окончания подписки (календарный день). Пусто — без срока",
    )

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
    registered_at: datetime | None = Field(
        default=None,
        description="Момент регистрации / создания записи (UTC); для старых записей может быть не задан",
    )
    telegram_id: int | None
    telegram_properties: dict[str, Any] | None = None
    email: str | None = None
    account_role: Literal["client", "manager", "admin"] = Field(
        default="client",
        description="client — клиент; manager — рефералы; admin — полный администратор",
    )
    subscription_until: date | None
    token: str = Field(
        description="Токен для URL /sub/{token} (Base64) и /sub/{token}/json",
    )
    vless_uuid: str = Field(description="UUID клиента VLESS (общий для всех узлов в подписке)")


class UserListItem(BaseModel):
    """Список пользователей для таблиц админки и менеджера (GET /users)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    registered_at: datetime | None = Field(
        default=None,
        description="Момент регистрации / создания записи (UTC)",
    )
    telegram_id: int | None
    telegram_properties: dict[str, Any] | None = None
    email: str | None = None
    account_role: Literal["client", "manager", "admin"] = Field(
        default="client",
        description="client — клиент; manager — рефералы; admin — полный администратор",
    )
    subscription_until: date | None
    total_traffic_bytes: int = Field(
        ge=0,
        description="Сумма up+down по всем узлам (user_server_traffic)",
    )
    referral_link_id: int | None = None
    token: str | None = Field(
        default=None,
        description="Токен подписки; у менеджера всегда null",
    )
    vless_uuid: str | None = Field(
        default=None,
        description="UUID VLESS; у менеджера всегда null",
    )


class UserUpdate(BaseModel):
    """Частичное обновление пользователя (админка)."""

    subscription_until: date | None = Field(
        default=None,
        description="Дата окончания подписки; null — без срока",
    )
    telegram_id: int | None = Field(
        default=None,
        ge=1,
        le=9223372036854775807,
        description="Telegram id; null — сбросить привязку (редко). Не указывайте поле, если не меняете.",
    )
    telegram_properties: dict[str, Any] | None = Field(
        default=None,
        description="JSON-поля Telegram; null — очистить",
    )
    account_role: Literal["client", "manager", "admin"] | None = Field(
        default=None,
        description="Назначение роли в БД (admin — полный доступ, manager — только рефералы)",
    )
    registered_at: datetime | None = Field(
        default=None,
        description="Момент регистрации (UTC); null — сбросить дату",
    )

    @field_validator("registered_at", mode="before")
    @classmethod
    def coerce_registered_at(cls, v: object) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        if isinstance(v, date) and not isinstance(v, datetime):
            return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                head = s[:10]
                try:
                    d_only = date.fromisoformat(head)
                except ValueError as e:
                    raise ValueError("registered_at: неверная дата") from e
                if len(s) == 10:
                    return datetime(
                        d_only.year,
                        d_only.month,
                        d_only.day,
                        tzinfo=timezone.utc,
                    )
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        raise ValueError(
            "registered_at: ожидается дата или дата-время в формате ISO (UTC)",
        )

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


class SubscriptionPayload(BaseModel):
    """Ответ по токену подписки: срок, узлы и готовые ссылки для VPN-клиентов (VLESS+REALITY)."""

    valid_until: date | None = Field(
        description="Подписка действительна до (включительно, календарная дата), null — без ограничения",
    )
    subscription_active: bool = Field(
        description="Если false (срок истёк), servers / vless_uris / subscription_base64 пустые",
    )
    servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Активные узлы: address, port, uuid, flow, sni, public_key, short_id, dest, server_names",
    )
    vless_uris: list[str] = Field(
        default_factory=list,
        description="Стандартные share-ссылки vless:// (v2rayN, v2rayNG, Nekoray, Streisand и др.)",
    )
    subscription_base64: str = Field(
        default="",
        description="Base64 от UTF-8 текста: по одной vless-ссылке на строку (как тело «subscription URL»)",
    )
