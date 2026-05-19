from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

StatsGranularity = Literal["day", "hour"]

from app.constants import BIGINT_MAX
from app.domain.models.auth import SubscriptionConnectionItem


class UsersCountResponse(BaseModel):
    users_count: int = Field(ge=0, description="Число записей в таблице users")


class StaffUserSearchItem(BaseModel):
    """Краткая карточка пользователя для автодополнения в админке."""

    id: int = Field(description="users.id")
    email: str | None = Field(default=None, description="Почта, если задана")
    telegram_id: int | None = Field(default=None, description="Числовой id в Telegram")
    telegram_username: str | None = Field(
        default=None,
        description="Ник из telegram_properties.username (без @)",
    )


class UserStatsByDateRow(BaseModel):
    """День UTC — счётчики за календарный день; почасовой ряд — накопление до конца часа по календарю Москвы."""

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
            "Момент начала периода (абсолютное время); в JSON сериализуется в московском времени. "
            "При day — полночь этого календарного дня UTC; при hour — начало часа по календарю Москвы."
        ),
    )
    users_count: int = Field(
        ge=0,
        description=(
            "При granularity=day — пользователей с этим календарным днём регистрации (UTC). "
            "При hour — всего пользователей строго до конца этого часа по Москве "
            "(включая без registered_at)."
        ),
    )
    users_with_traffic_count: int = Field(
        ge=0,
        description=(
            "При day — с этим днём регистрации и ненулевым суммарным трафиком (последний снимок на узел). "
            "При hour — пользователей с трафиком среди учтённых на конец часа "
            "(включая без registered_at)."
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
            "(min created_at по пользователю). При hour — пользователей, у кого это минимальное время "
            "строго до конца часа по календарю Москвы."
        ),
    )
    users_cumulative_traffic_over_100_mbit_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: число пользователей, у которых на конец этого UTC-дня суммарный "
            "накопленный трафик (последний снимок на узел, как в метрике active_users_count) "
            "строго больше 100 Мбит объёма (100×10⁶ бит → байты). При hour — 0."
        ),
    )
    persistent_traffic_users_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: пользователи с ростом суммарного трафика в этот UTC-день "
            "(как active_users_count), для которых это не первый такой «активный» день — "
            "раньше уже был день с ростом. При hour — 0."
        ),
    )
    users_with_payment_count: int = Field(
        default=0,
        ge=0,
        description=(
            "При granularity=day — число пользователей, у которых первый платёж "
            "(минимум payments.created_at в календарном дне UTC) приходится на этот stats_date. "
            "При hour — 0."
        ),
    )
    active_users_with_payment_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: как active_users_count, но только пользователи, у которых "
            "к концу этого UTC-дня уже была хотя бы одна оплата (первая оплата не позже этого дня). "
            "При hour — 0."
        ),
    )
    users_with_active_subscription_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: число пользователей с активной подпиской на конец "
            "этого UTC-календарного дня (subscription_until IS NULL или >= дня; учтены только "
            "уже зарегистрированные к этому дню). При hour — 0."
        ),
    )


class UsersDailyStatsResponse(BaseModel):
    """Сводка пользовательской статистики: по UTC-дням или по московским часам (поля времени в JSON — Москва)."""

    granularity: StatsGranularity = Field(
        default="day",
        description=(
            "day — календарные дни UTC; hour — 24 часа календарного дня Europe/Moscow (hour_day)"
        ),
    )
    hour_day: date | None = Field(
        default=None,
        description=(
            "При granularity=hour — календарная дата суток по Москве (YYYY-MM-DD), те же сутки, что в запросе."
        ),
    )
    stats_by_date: list[UserStatsByDateRow] = Field(
        description=(
            "При granularity=day — дни по возрастанию stats_date; строка без даты — в конце. "
            "При granularity=hour — ровно 24 строки (часы 00–23 МСК выбранного hour_day)."
        ),
    )
    hour_baseline_users_count: int | None = Field(
        default=None,
        description=(
            "Только granularity=hour: накопление пользователей на начало суток МСК выбранного hour_day "
            "(для прироста относительно первого часа)."
        ),
    )
    hour_baseline_users_with_traffic_count: int | None = Field(
        default=None,
        description="Только granularity=hour: то же для пользователей с трафиком.",
    )
    hour_baseline_subscription_devices_users_count: int | None = Field(
        default=None,
        description="Только granularity=hour: то же для первых записей subscription_devices.",
    )
    hour_undated_users_count: int | None = Field(
        default=None,
        description="Только granularity=hour: пользователи без registered_at (уже включены в hour_baseline_* и в каждый час).",
    )


class DailyPaymentsExpiryStatsRow(BaseModel):
    """Одна точка столбчатого графика: оплаты и разбивка по UTC-дню subscription_until."""

    stats_date: date
    payments_count: int = Field(ge=0, description="Число строк payments за этот календарный день UTC")
    subscription_expiring_total_count: int = Field(
        ge=0,
        description="Пользователи с subscription_until = этот UTC-день (сумма четырёх групп ниже)",
    )
    subscription_expiring_active_today_count: int = Field(
        ge=0,
        description=(
            "С subscription_until = этот stats_date: рост суммарного трафика в **текущий** "
            "календарный день UTC (как «активные сегодня» в daily_stats), в том числе для столбца будущего "
            "окончания — уже «живые» пользователи по трафику сегодня"
        ),
    )
    subscription_expiring_active_on_day_count: int = Field(
        ge=0,
        description=(
            "Истекают в этот UTC-день: рост суммарного трафика в день stats_date, "
            "и при этом нет роста в текущий UTC-день (иначе — в subscription_expiring_active_today_count)"
        ),
    )
    subscription_expiring_has_traffic_count: int = Field(
        ge=0,
        description=(
            "Истекают в этот день: без роста трафика ни в текущий UTC-день, ни в день stats_date, "
            "но когда-либо был ненулевой суммарный трафик"
        ),
    )
    subscription_expiring_no_traffic_count: int = Field(
        ge=0,
        description="Истекают в этот день, без трафика (как «серые» на графике)",
    )


class DailyPaymentsExpiryStatsResponse(BaseModel):
    rows: list[DailyPaymentsExpiryStatsRow] = Field(
        description="Дни по возрастанию stats_date (UTC); при month=YYYY-MM — все дни месяца; сумма четырёх групп окончания = subscription_expiring_total_count",
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
        description="Токен для URL /sub/{token} (подписка) и /sub/{token}/clash (YAML)",
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
    active_today: bool = Field(
        default=False,
        description=(
            "Календарный день UTC: сумма по узлам последних снимков с traffic_date ≤ сегодня "
            "больше, чем сумма последних снимков строго до сегодняшнего дня (traffic_date < сегодня) "
            "— то есть накопленные счётчики выросли относительно предыдущего известного снимка, "
            "а не только относительно строки с датой «вчера»"
        ),
    )
    has_payments: bool = Field(
        default=False,
        description="Есть хотя бы одна запись в таблице payments",
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
    referral_link_id: int | None = Field(
        default=None,
        description=(
            "Идентификатор реферальной ссылки, зафиксированной при регистрации пользователя "
            "(атрибуция / источник привлечения)"
        ),
    )
    owned_referral_link_id: int | None = Field(
        default=None,
        description=(
            "Персональная ссылка пользователя как владельца (referral_links.owner_kind=user); "
            "null, если запись ещё не создавалась"
        ),
    )
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
