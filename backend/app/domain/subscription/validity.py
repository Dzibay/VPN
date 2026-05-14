"""Правила действия подписки пользователя (календарная дата UTC)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_

from app.constants import (
    TRIAL_DAYS_AFTER_REGISTRATION,
    TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION,
)
from app.core.time import utc_today
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


def user_has_active_subscription(user: User) -> bool:
    if user.subscription_until is None:
        return True
    return user.subscription_until >= utc_today()


def subscription_active_sql():
    return or_(
        User.subscription_until.is_(None),
        User.subscription_until >= utc_today(),
    )
