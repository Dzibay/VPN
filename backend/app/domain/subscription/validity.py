"""Правила действия подписки пользователя (календарная дата UTC)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_

from app.constants import TRIAL_DAYS_AFTER_REGISTRATION
from app.core.time import utc_today
from app.infrastructure.persistence.models.user import User


def subscription_until_after_registration() -> date:
    """Дата окончания подписки для нового пользователя (сегодня UTC + пробный период)."""

    return utc_today() + timedelta(days=TRIAL_DAYS_AFTER_REGISTRATION)


def user_has_active_subscription(user: User) -> bool:
    if user.subscription_until is None:
        return True
    return user.subscription_until >= utc_today()


def subscription_active_sql():
    return or_(
        User.subscription_until.is_(None),
        User.subscription_until >= utc_today(),
    )
