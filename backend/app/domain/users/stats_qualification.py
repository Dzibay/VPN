"""Критерий включения пользователя в админскую статистику.

Учитываются только пользователи с привязанным Telegram **или** с подтверждённой почтой.
Записи без Telegram и с неподтверждённым email в основные метрики не входят.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, func, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.infrastructure.persistence.models.user import User


def user_identity_confirmed_sql(
    user: type[User] | InstrumentedAttribute = User,
) -> ColumnElement[bool]:
    """Telegram привязан или email подтверждён (общий критерий «реального» аккаунта)."""
    return or_(
        user.telegram_id.is_not(None),
        and_(
            user.email.is_not(None),
            func.trim(user.email) != "",
            user.email_verified_at.is_not(None),
        ),
    )


def user_counts_in_admin_stats(
    user: type[User] | InstrumentedAttribute = User,
) -> ColumnElement[bool]:
    """SQL-условие: пользователь входит в сводную статистику админки."""
    return user_identity_confirmed_sql(user)


def user_unverified_email_without_telegram(
    user: type[User] | InstrumentedAttribute = User,
) -> ColumnElement[bool]:
    """Нет Telegram и email не подтверждён (исключены из основной статистики)."""
    return and_(
        user.telegram_id.is_(None),
        user.email.is_not(None),
        func.trim(user.email) != "",
        user.email_verified_at.is_(None),
    )
