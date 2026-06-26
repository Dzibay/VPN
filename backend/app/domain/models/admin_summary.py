from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class AdminSummaryResponse(BaseModel):
    period_from: date
    period_to: date
    msk_today: date

    users_total: int = Field(ge=0, description="Всего учётных пользователей")
    users_in_period: int = Field(ge=0, description="Новых пользователей за период (МСК)")

    active_users: int = Field(ge=0, description="Активная подписка (subscription_until ≥ сегодня МСК)")
    active_users_pct: float = Field(
        ge=0,
        description="Доля активных от users_total, %",
    )

    expiring_subscriptions: int = Field(
        ge=0,
        description="Подписка истекает менее чем через 7 дней (включая сегодня)",
    )
    expiring_paid: int = Field(ge=0, description="Истекающие с хотя бы одной оплатой")

    revenue_period: Decimal = Field(description="Доход за период (валовый, payments.amount)")
    revenue_total: Decimal = Field(description="Доход за всё время (валовый)")

    avg_check: Decimal = Field(description="Средний чек за период")
    payments_count: int = Field(ge=0, description="Число платежей за период")

    avg_revenue_per_paying_user: Decimal = Field(
        description="Средний суммарный доход с платящего пользователя (всё время)",
    )
    paying_users_total: int = Field(ge=0, description="Всего платящих пользователей")

    conversion_pct: float = Field(
        ge=0,
        description="Конверсия: paying_users_total / users_total, %",
    )

    paying_users_in_period: int = Field(
        ge=0,
        description="Уникальных платящих за период (МСК)",
    )
    ltv_period: Decimal = Field(
        description="LTV за период: revenue_period / paying_users_in_period",
    )
    payments_per_paying_user: float = Field(
        ge=0,
        description="Среднее число платежей на платящего за период",
    )
    renewal_pct: float = Field(
        ge=0,
        description="Удержание: (renewed_on_expiry + renewed_early) / renewal_eligible, %",
    )
    return_pct: float = Field(
        ge=0,
        description="Возвратность: returned_after_expiry / renewal_eligible, %",
    )
    renewal_eligible: int = Field(
        ge=0,
        description="Расчётных окончаний подписки (months×31) в периоде",
    )
    renewed_on_expiry: int = Field(
        ge=0,
        description="Следующая оплата ровно в день расчётного окончания",
    )
    renewed_early: int = Field(
        ge=0,
        description="Следующая оплата до расчётного окончания (досрочно)",
    )
    returned_after_expiry: int = Field(
        ge=0,
        description="Следующая оплата позже окончания, в пределах периода",
    )
