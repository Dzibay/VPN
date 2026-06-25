from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StatsGranularity = Literal["day", "hour"]

from app.constants import BIGINT_MAX
from app.core.time import ensure_utc
from app.domain.models.auth import SubscriptionConnectionItem

ReferralBonusPolicy = Literal[
    "default",
    "fixed_first_payment_instant",
    "fixed_first_payment_balance",
]


class UsersCountResponse(BaseModel):
    users_count: int = Field(
        ge=0,
        description=(
            "Число пользователей в статистике: Telegram привязан "
            "или email подтверждён"
        ),
    )
    unverified_email_users_count: int = Field(
        ge=0,
        description=(
            "Пользователи без Telegram с непустым, но неподтверждённым email "
            "(не входят в users_count)"
        ),
    )
    registrations_today_count: int = Field(
        ge=0,
        description=(
            "Регистрации за текущий календарный день Europe/Moscow среди "
            "учётных пользователей (Telegram или подтверждённый email)"
        ),
    )
    registrations_today_unverified_email_count: int = Field(
        ge=0,
        description=(
            "Регистрации за сегодня (МСK) без Telegram и с неподтверждённым email "
            "(не входят в registrations_today_count)"
        ),
    )
    registrations_yesterday_count: int = Field(
        ge=0,
        description=(
            "Регистрации за предыдущий календарный день Europe/Moscow "
            "(те же фильтры, что registrations_today_count)"
        ),
    )
    registration_gap_overall_ms: float | None = Field(
        default=None,
        description="Средний интервал между соседними registered_at (UTC), мс; null если < 2 дат",
    )
    registration_gap_today_ms: float | None = Field(
        default=None,
        description="То же только для регистраций за сегодня UTC; null если < 2 дат",
    )


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
    """День МСК — счётчики за календарный день Europe/Moscow; почасовой ряд — до конца часа по Москве."""

    stats_date: date | None = Field(
        description=(
            "Календарный день Europe/Moscow при granularity=day (registered_at, оплаты, устройства); "
            "при granularity=hour — всегда null (используйте period_start_utc). "
            "null также означает агрегат по пользователям без registered_at."
        ),
    )
    period_start_utc: datetime | None = Field(
        default=None,
        description=(
            "Момент начала периода (абсолютное время); в JSON сериализуется в московском времени. "
            "При day — полночь этого календарного дня по Москве; при hour — начало часа по Москве."
        ),
    )
    users_count: int = Field(
        ge=0,
        description=(
            "При granularity=day — прирост по календарному дню регистрации (МСК) для всех с registered_at; "
            "без registered_at — одна строка stats_date=null. "
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
            "При granularity=day — число пользователей, у которых на этот stats_date "
            "(по traffic_date, снимки в UTC-календаре) суммарный трафик вырос относительно предыдущего дня. "
            "При granularity=hour всегда 0 (в БД нет почасовых снимков трафика)."
        ),
    )
    subscription_devices_users_count: int = Field(
        ge=0,
        description=(
            "При day — впервые получили запись subscription_devices в этот календарный день МСК "
            "(min created_at по пользователю). При hour — пользователей, у кого это минимальное время "
            "строго до конца часа по календарю Москвы."
        ),
    )
    users_cumulative_traffic_over_100_mbit_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: число пользователей, у которых на конец этого stats_date суммарный "
            "накопленный трафик (последний снимок на узел, как в метрике active_users_count) "
            "строго больше 100 Мбит объёма (100×10⁶ бит → байты). При hour — 0."
        ),
    )
    persistent_traffic_users_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: пользователи с ростом суммарного трафика в этот день "
            "(как active_users_count), для которых это не первый такой «активный» день — "
            "раньше уже был день с ростом. При hour — 0."
        ),
    )
    users_with_payment_count: int = Field(
        default=0,
        ge=0,
        description=(
            "При granularity=day — число пользователей, у которых первый платёж "
            "(минимум payments.created_at в календарном дне МСК) приходится на этот stats_date. "
            "При hour — 0."
        ),
    )
    payments_first_count: int = Field(
        default=0,
        ge=0,
        description=(
            "При granularity=day — число платежей (строк payments), которые являются "
            "первой оплатой пользователя в этот календарный день МСК. При hour — 0."
        ),
    )
    payments_repeat_count: int = Field(
        default=0,
        ge=0,
        description=(
            "При granularity=day — число повторных платежей (не первая оплата пользователя) "
            "в этот календарный день МСК. При hour — 0."
        ),
    )
    active_users_with_payment_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: как active_users_count, но только пользователи, у которых "
            "к концу этого stats_date уже была хотя бы одна оплата (первая оплата не позже этого дня). "
            "При hour — 0."
        ),
    )
    users_with_active_subscription_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Только granularity=day: число пользователей с активной подпиской на конец "
            "этого календарного дня МСК (subscription_until >= дня; учтены только "
            "уже зарегистрированные к этому дню). При hour — 0."
        ),
    )


class UsersDailyStatsResponse(BaseModel):
    """Сводка пользовательской статистики: по дням МСК или по московским часам (поля времени в JSON — Москва)."""

    granularity: StatsGranularity = Field(
        default="day",
        description=(
            "day — календарные дни Europe/Moscow; hour — 24 часа календарного дня Europe/Moscow (hour_day)"
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
    day_baseline_users_count: int | None = Field(
        default=None,
        description=(
            "Только granularity=day при заданном from: сумма users_count по дням МСК строго до from "
            "(для накопительных графиков на частичном диапазоне)."
        ),
    )
    day_baseline_users_with_traffic_count: int | None = Field(
        default=None,
        description="Только granularity=day при from: сумма users_with_traffic_count до from.",
    )
    day_baseline_subscription_devices_users_count: int | None = Field(
        default=None,
        description="Только granularity=day при from: сумма subscription_devices_users_count до from.",
    )
    day_baseline_users_with_payment_count: int | None = Field(
        default=None,
        description="Только granularity=day при from: сумма users_with_payment_count до from.",
    )


class DailyPaymentsExpiryStatsRow(BaseModel):
    """Одна точка столбчатого графика: оплаты и разбивка по дню subscription_until (МСК)."""

    stats_date: date
    payments_count: int = Field(ge=0, description="Число строк payments за этот календарный день Europe/Moscow")
    payments_first_count: int = Field(
        ge=0,
        description="Оплаты за день, которые являются первой оплатой пользователя (по created_at, id)",
    )
    payments_repeat_count: int = Field(
        ge=0,
        description="Оплаты за день от пользователей с хотя бы одной более ранней оплатой",
    )
    subscription_expiring_has_payment_count: int = Field(
        ge=0,
        description="Пользователи с subscription_until = этот день МСК и хотя бы одной оплатой когда-либо",
    )
    subscription_expiring_total_count: int = Field(
        ge=0,
        description="Пользователи с subscription_until = этот день по Москве (сумма четырёх групп ниже)",
    )
    subscription_expiring_active_today_count: int = Field(
        ge=0,
        description=(
            "С subscription_until = этот stats_date: рост суммарного трафика в **текущий** "
            "календарный день МСК (как «активные сегодня» в daily_stats), в том числе для столбца будущего "
            "окончания — уже «живые» пользователи по трафику сегодня"
        ),
    )
    subscription_expiring_active_on_day_count: int = Field(
        ge=0,
        description=(
            "Истекают в этот день МСК: рост суммарного трафика в день stats_date, "
            "и при этом нет роста в текущий день МСК (иначе — в subscription_expiring_active_today_count)"
        ),
    )
    subscription_expiring_has_traffic_count: int = Field(
        ge=0,
        description=(
            "Истекают в этот день: без роста трафика ни в текущий день МСК, ни в день stats_date, "
            "но когда-либо был ненулевой суммарный трафик"
        ),
    )
    subscription_expiring_no_traffic_count: int = Field(
        ge=0,
        description="Истекают в этот день, без трафика (как «серые» на графике)",
    )


class DailyPaymentsExpiryStatsResponse(BaseModel):
    rows: list[DailyPaymentsExpiryStatsRow] = Field(
        description=(
            "Дни по возрастанию stats_date (МСК); при month=YYYY-MM — все дни месяца по Москве; "
            "payments_first_count + payments_repeat_count = payments_count; "
            "сумма четырёх групп трафика окончания = subscription_expiring_total_count; "
            "subscription_expiring_has_payment_count — подмножество истекающих с оплатой"
        ),
    )
    month_min: str | None = Field(
        default=None,
        description=(
            "Первый доступный месяц YYYY-MM (МСК): самый ранний календарный месяц с оплатой "
            "или окончанием подписки"
        ),
    )
    month_max: str | None = Field(
        default=None,
        description=(
            "Последний доступный месяц YYYY-MM (МСК): самый последний календарный месяц с оплатой "
            "или окончанием подписки; может быть в будущем"
        ),
    )


PayExpDayDetailGroupKey = Literal[
    "payments_first",
    "payments_repeat",
    "expiry_no_traffic",
    "expiry_has_traffic",
    "expiry_active_on_day",
    "expiry_active_today",
]


class PayExpDayUserItem(BaseModel):
    """Пользователь в группе окончания подписки за выбранный день МСК."""

    user_id: int = Field(description="users.id")
    email: str | None = Field(default=None, description="Почта, если задана")
    telegram_id: int | None = Field(default=None, description="Числовой id в Telegram")
    telegram_username: str | None = Field(
        default=None,
        description="Ник из telegram_properties.username (без @)",
    )
    subscription_until: date | None = Field(
        default=None,
        description="Дата окончания подписки по Москве",
    )
    has_payments_ever: bool = Field(
        default=False,
        description="Был хотя бы один платёж когда-либо",
    )
    did_not_renew: bool = Field(
        default=False,
        description=(
            "Только группы окончания: была оплата, subscription_until = stats_date "
            "и нет платежа в этот день (не продлил подписку)"
        ),
    )


class PayExpDayPaymentItem(BaseModel):
    """Один платёж за выбранный календарный день Europe/Moscow."""

    payment_id: int = Field(description="payments.id")
    user_id: int = Field(description="users.id")
    email: str | None = Field(default=None, description="Почта, если задана")
    telegram_id: int | None = Field(default=None, description="Числовой id в Telegram")
    telegram_username: str | None = Field(
        default=None,
        description="Ник из telegram_properties.username (без @)",
    )
    amount_rub: Decimal = Field(description="Сумма платежа (payments.amount)")
    provider: str = Field(description="Провайдер платежа (payments.provider)")
    is_first_payment: bool = Field(
        description="True, если это первая оплата пользователя по created_at, id",
    )
    payment_at: datetime = Field(
        description="Момент создания платежа (в JSON — московское время)",
    )


class PayExpDayDetailGroup(BaseModel):
    """Одна категория столбчатого графика с детализацией по пользователям или платежам."""

    key: PayExpDayDetailGroupKey
    title: str
    hint: str
    count: int = Field(ge=0)
    paid_users_count: int = Field(
        default=0,
        ge=0,
        description="Группы окончания: пользователи с хотя бы одной оплатой когда-либо",
    )
    did_not_renew_count: int = Field(
        default=0,
        ge=0,
        description="Группы окончания: оплачивали, но подписка заканчивается в этот день без оплаты в этот день",
    )
    users: list[PayExpDayUserItem] = Field(default_factory=list)
    payments: list[PayExpDayPaymentItem] = Field(default_factory=list)


class DailyPaymentsExpiryDayDetailResponse(BaseModel):
    """Детализация по одному дню МСК для виджета под графиком «Оплаты и окончания подписки»."""

    stats_date: date = Field(description="Выбранный календарный день Europe/Moscow")
    groups: list[PayExpDayDetailGroup] = Field(
        description="Группы в порядке легенды графика; пустые группы не включаются",
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


class StaffUsersBulkDeleteBody(BaseModel):
    ids: list[int] = Field(
        min_length=1,
        max_length=500,
        description="Список users.id для удаления",
    )


class StaffUsersBulkDeleteResponse(BaseModel):
    deleted_count: int = Field(ge=0, description="Число удалённых пользователей")


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
        description="Последний день подписки по календарю Europe/Moscow. Пусто — без срока",
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
    traffic_limit_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Персональный потолок трафика (байты); null — без лимита.",
    )
    token: str = Field(
        description="Токен для URL /sub/{token} (подписка) и /sub/{token}/clash (YAML)",
    )
    vless_uuid: str = Field(description="UUID клиента VLESS (общий для всех узлов в подписке)")
    referral_bonus_policy: ReferralBonusPolicy = Field(
        default="default",
        description=(
            "Условия начисления реферальных бонусов: default — месяцы × глобальный коэффициент, "
            "активация при оплате реферера; fixed_first_payment_instant — +20 дней при первой "
            "оплате каждого друга, сразу на subscription_until; fixed_first_payment_balance — "
            "фиксированная сумма на баланс при первой оплате каждого друга"
        ),
    )
    balance_rub: Decimal = Field(
        ge=0,
        description="Накопленный баланс пользователя (руб.), из users.balance_kopecks",
    )
    referral_fixed_bonus_rub: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Персональная сумма реферального бонуса на баланс (руб.); null — глобальный дефолт "
            "из REFERRAL_FIXED_FIRST_PAYMENT_BONUS_RUB"
        ),
    )
    referral_fixed_bonus_rub_default: int = Field(
        ge=1,
        description="Глобальный дефолт суммы реферального бонуса на баланс (руб.)",
    )

    @model_validator(mode="before")
    @classmethod
    def inject_balance_fields_from_user_orm(cls, data: object) -> object:
        from app.domain.users.staff_balance_fields import staff_user_balance_fields
        from app.infrastructure.persistence.models.user import User

        if isinstance(data, User):
            payload = {
                "id": data.id,
                "registered_at": data.registered_at,
                "telegram_id": data.telegram_id,
                "telegram_properties": data.telegram_properties,
                "email": data.email,
                "account_role": data.account_role,
                "subscription_until": data.subscription_until,
                "traffic_limit_bytes": data.traffic_limit_bytes,
                "token": data.token,
                "vless_uuid": data.vless_uuid,
                "referral_bonus_policy": data.referral_bonus_policy,
                **staff_user_balance_fields(data),
            }
            return payload
        return data


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
    email_verified: bool = Field(
        default=False,
        description="True, если задан email и он подтверждён (email_verified_at в БД).",
    )
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
    traffic_limit_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Персональный потолок трафика (байты); NULL — без лимита (обычно после оплаты)",
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
    referral_bonus_policy: ReferralBonusPolicy = Field(
        default="default",
        description="Индивидуальные условия реферальных бонусов для этого пользователя как реферера",
    )
    balance_rub: Decimal = Field(
        ge=0,
        description="Накопленный баланс пользователя (руб.)",
    )
    referral_fixed_bonus_rub: int | None = Field(
        default=None,
        ge=1,
        description="Персональная сумма реферального бонуса на баланс (руб.); null — глобальный дефолт",
    )
    referral_fixed_bonus_rub_default: int = Field(
        ge=1,
        description="Глобальный дефолт суммы реферального бонуса на баланс (руб.)",
    )
    token: str | None = Field(
        default=None,
        description="Токен подписки; у менеджера всегда null",
    )
    vless_uuid: str | None = Field(
        default=None,
        description="UUID VLESS; у менеджера всегда null",
    )


class StaffUsersListResponse(BaseModel):
    """Пагинированный список пользователей для админки (GET /users)."""

    items: list[UserListItem] = Field(description="Строки users, новые id первыми")
    total: int = Field(ge=0, description="Число записей с учётом фильтра referral_link_id")
    limit: int = Field(ge=1, description="Размер страницы")
    offset: int = Field(ge=0, description="Смещение от начала отсортированного списка")


class UserUpdate(BaseModel):
    """Частичное обновление пользователя (админка)."""

    subscription_until: date | None = Field(
        default=None,
        description="Последний день подписки по календарю Europe/Moscow; null — без срока",
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
    traffic_limit_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Персональный потолок трафика (байты); null — без лимита",
    )
    referral_bonus_policy: ReferralBonusPolicy | None = Field(
        default=None,
        description=(
            "Условия реферальных бонусов: default | fixed_first_payment_instant | "
            "fixed_first_payment_balance; не указывайте поле, если не меняете"
        ),
    )
    referral_fixed_bonus_rub: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description=(
            "Персональная сумма реферального бонуса на баланс (руб.); null — сбросить override "
            "и использовать глобальный дефолт. Имеет смысл при политике fixed_first_payment_balance."
        ),
    )

    @field_validator("registered_at", mode="before")
    @classmethod
    def coerce_registered_at(cls, v: object) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return ensure_utc(v)
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
            return ensure_utc(dt)
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
