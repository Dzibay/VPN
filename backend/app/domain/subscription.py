"""Правила действия подписки пользователя (календарная дата)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_

from app.models.user import User


def user_has_active_subscription(user: User) -> bool:
    if user.subscription_until is None:
        return True
    return user.subscription_until >= date.today()


def subscription_active_sql():
    return or_(
        User.subscription_until.is_(None),
        User.subscription_until >= date.today(),
    )
