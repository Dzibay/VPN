"""Правила действия подписки (календарная дата UTC и персональный лимит трафика)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, not_, or_

from app.constants import (
    TRIAL_DAYS_AFTER_REGISTRATION,
    TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION,
)
from app.core.time import utc_today
from app.domain.user_traffic import user_traffic_over_limit_sql
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


def trial_extra_days_for_referral_link(link: ReferralLink | None) -> int:
    """Дополнительные дни триала при регистрации по персональной ссылке пользователя."""

    if link is None or link.owner_kind != "user":
        return 0
    return int(TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION)


def subscription_until_after_registration(*, extra_trial_days: int = 0) -> date:
    """Дата окончания подписки для нового пользователя (сегодня UTC + пробный период + опциональный бонус)."""

    days = int(TRIAL_DAYS_AFTER_REGISTRATION) + max(0, int(extra_trial_days))
    return utc_today() + timedelta(days=days)


def subscription_calendar_active(user: User) -> bool:
    """Подписка по дате ``subscription_until`` (без учёта лимита трафика)."""
    if user.subscription_until is None:
        return True
    return user.subscription_until >= utc_today()


def subscription_calendar_active_sql():
    """SQL: календарная подписка активна (дата ≥ сегодня UTC или без срока)."""
    return or_(
        User.subscription_until.is_(None),
        User.subscription_until >= utc_today(),
    )


def user_has_active_subscription(user: User, *, used_bytes: int | None = None) -> bool:
    """
    Доступ к VPN: календарь активен и (без лимита или трафик строго ниже ``traffic_limit_bytes``).

    Если задан лимит, передайте ``used_bytes`` (сумма up+down), иначе лимит не учитывается.
    """
    if not subscription_calendar_active(user):
        return False
    limit = user.traffic_limit_bytes
    if limit is None:
        return True
    if used_bytes is None:
        return False
    return int(used_bytes) < int(limit)


def subscription_active_sql():
    """SQL для списка клиентов Xray: календарь активен и трафик ниже персонального лимита."""
    return and_(
        subscription_calendar_active_sql(),
        not_(User.id.in_(user_traffic_over_limit_sql())),
    )
