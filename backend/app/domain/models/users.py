from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

StatsGranularity = Literal["day", "hour"]

from app.constants import BIGINT_MAX
from app.domain.models.auth import SubscriptionConnectionItem


class UsersCountResponse(BaseModel):
    users_count: int = Field(ge=0, description="Число записей в таблице users")


class UserStatsByDateRow(BaseModel):
    """Показатели по гранулярности: день UTC — счётчики за календарный день; час UTC — накопление до конца часа."""

    stats_date: date | None = Field(
        description=(
            "Календарный день UTC при granularity=day (по registered_at); "
            "при granularity=hour — всегда null (используйте period_start_utc). "
            "null также означает агрегат по пользователям без registered_at."
        ),
    )
    period_start_utc: datetime | None = Field(
        default=None,
        description=(
            "Начало периода в UTC; в JSON сериализуется в московском времени. "
            "При day — полночь этого календарного дня UTC; при hour — начало часа UTC."
        ),
    )
    users_count: int = Field(
        ge=0,
        description=(
            "При granularity=day — пользователей с этим календарным днём регистрации (UTC). "
            "При hour — всего пользователей с известным registered_at строго до конца этого часа UTC."
        ),
    )
    users_with_traffic_count: int = Field(
        ge=0,
        description=(
            "При day — с этим днём регистрации и ненулевым суммарным трафиком (последний снимок на узел). "
            "При hour — таких пользователей среди уже зарегистрированных до конца часа."
        ),
    )
    active_users_count: int = Field(
        ge=0,
        description=(
            "При granularity=day — число пользователей, у которых на этот календарный день UTC "
            "(по traffic_date) суммарный накопленный трафик вырос относительно предыдущего дня. "
            "При granularity=hour всегда 0 (в БД нет почасовых снимков трафика)."
        ),
    )
    subscription_devices_users_count: int = Field(
        ge=0,
        description=(
            "При day — впервые получили запись subscription_devices в этот календарный день UTC "
            "(min created_at по пользователю). При hour — пользователей, у кого это минимальное время строго до конца часа UTC."
        ),
    )


class UsersDailyStatsResponse(BaseModel):
    """Сводка пользовательской статистики по UTC: по дням или по часам (поля времени в JSON — Москва)."""

    granularity: StatsGranularity = Field(
        default="day",
        description="day — календарные дни UTC; hour — 24 часа UTC внутри календарного дня hour_day",
    )
    hour_day: date | None = Field(
        default=None,
        description=(
            "При granularity=hour — выбранный календарный день UTC (те же сутки, что и в запросе hour_day)"
        ),
    )
    stats_by_date: list[UserStatsByDateRow] = Field(
        description=(
            "При granularity=day — дни по возрастанию stats_date; строка без даты — в конце. "
            "При granularity=hour — ровно 24 строки (часы 00–23 UTC выбранного hour_day)."
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
        le=BIGINT_MAX,
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
    subscription_devices_count: int = Field(
        ge=0,
        description="Число записей subscription_devices (подключённых устройств по подписке)",
    )
    subscription_devices: list[SubscriptionConnectionItem] = Field(
        default_factory=list,
        description=(
            "Список подключений по подписке (как subscription_connections в ЛК): "
            "по убыванию updated_at"
        ),
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
        le=BIGINT_MAX,
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
