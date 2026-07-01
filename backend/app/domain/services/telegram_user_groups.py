"""Группы пользователей для GET /api/telegram/users (рассылки и сценарии Telegram-бота)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import and_, exists, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.subscription.validity import subscription_active_sql
from app.domain.user_traffic import user_traffic_over_limit_sql
from app.domain.tenant.project_context import get_current_project
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.user import User

TelegramUserGroup = Literal[
    "active",
    "active_pay",
    "active_free",
    "no_active",
    "no_active_pay",
    "no_active_free",
    "no_active_free_no_traffic",
    "no_active_free_no_date",
]

TELEGRAM_USER_GROUPS: tuple[TelegramUserGroup, ...] = (
    "active",
    "active_pay",
    "active_free",
    "no_active",
    "no_active_pay",
    "no_active_free",
    "no_active_free_no_traffic",
    "no_active_free_no_date",
)


def _telegram_users_base():
    return User.telegram_id.isnot(None)


def _subscription_active_for_group():
    """Активные: без срока или дата окончания ≥ сегодня (МСК), трафик ниже лимита."""
    return subscription_active_sql()


def _traffic_limit_exhausted():
    return User.id.in_(user_traffic_over_limit_sql())


def _has_payments():
    return exists(select(Payment.id).where(Payment.user_id == User.id))


def _not_active():
    return not_(_subscription_active_for_group())


def _free():
    return not_(_has_payments())


_GROUP_CONDITIONS: dict[TelegramUserGroup, object] = {
    "active": _subscription_active_for_group(),
    "active_pay": and_(_subscription_active_for_group(), _has_payments()),
    "active_free": and_(_subscription_active_for_group(), _free()),
    "no_active": _not_active(),
    "no_active_pay": and_(_not_active(), _has_payments()),
    "no_active_free": and_(_not_active(), _free()),
    "no_active_free_no_traffic": and_(_not_active(), _free(), _traffic_limit_exhausted()),
    "no_active_free_no_date": and_(_not_active(), _free(), not_(_traffic_limit_exhausted())),
}


async def list_telegram_user_ids_by_group(
    session: AsyncSession,
    group: TelegramUserGroup,
    *,
    project_id: int | None = None,
) -> list[int]:
    pid = project_id
    if pid is None:
        project = get_current_project()
        if project is None:
            return []
        pid = int(project.id)
    stmt = (
        select(User.telegram_id)
        .where(
            User.project_id == int(pid),
            _telegram_users_base(),
            _GROUP_CONDITIONS[group],
        )
        .order_by(User.telegram_id.asc())
    )
    rows = (await session.scalars(stmt)).all()
    return [int(tid) for tid in rows]
