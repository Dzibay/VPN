"""Правила действия подписки (календарная дата по Москве и персональный лимит трафика)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, not_, or_

from app.core.time import moscow_today
from app.domain.tenant.project_trial import resolve_project_trial_settings
from app.domain.user_traffic import user_traffic_over_limit_sql
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


def trial_extra_days_for_referral_link(link: ReferralLink | None, *, cfg: object | None = None) -> int:
    """Дополнительные дни триала при регистрации по персональной ссылке пользователя."""

    if link is None or link.owner_kind != "user":
        return 0
    return resolve_project_trial_settings(cfg).trial_extra_days_referral_registration


def subscription_until_after_registration(*, extra_trial_days: int = 0, cfg: object | None = None) -> date:
    """Дата окончания подписки для нового пользователя (сегодня по Москве + пробный период + бонус)."""

    trial = resolve_project_trial_settings(cfg)
    days = trial.trial_days_after_registration + max(0, int(extra_trial_days))
    return moscow_today() + timedelta(days=days)


def subscription_calendar_active(user: User) -> bool:
    """Подписка по дате ``subscription_until`` (без учёта лимита трафика)."""
    if user.subscription_until is None:
        return True
    return user.subscription_until >= moscow_today()


def subscription_calendar_active_sql():
    """SQL: календарная подписка активна (дата ≥ сегодня по Москве или без срока)."""
    return or_(
        User.subscription_until.is_(None),
        User.subscription_until >= moscow_today(),
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
