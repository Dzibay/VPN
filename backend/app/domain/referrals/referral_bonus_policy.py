"""Индивидуальные политики реферальных бонусов (``users.referral_bonus_policy``)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.constants import (
    REFERRAL_BONUS_FIXED_FIRST_PAYMENT_DAYS,
    REFERRAL_BONUS_POLICIES,
    REFERRAL_BONUS_POLICY_DEFAULT,
    REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE,
    REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT,
)
from app.domain.balance.money import rub_to_kopecks
from app.domain.tasks.notification_task_types import NOTIFY_REF_PAY
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


def normalize_referral_bonus_policy(raw: str | None) -> str:
    policy = (raw or REFERRAL_BONUS_POLICY_DEFAULT).strip()
    if policy not in REFERRAL_BONUS_POLICIES:
        return REFERRAL_BONUS_POLICY_DEFAULT
    return policy


def referral_bonus_applies_immediately(policy: str) -> bool:
    normalized = normalize_referral_bonus_policy(policy)
    return normalized in (
        REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT,
        REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE,
    )


def referral_bonus_policy_is_balance(policy: str) -> bool:
    return normalize_referral_bonus_policy(policy) == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE


def effective_referral_fixed_bonus_kopecks(owner: User, settings: Settings) -> int:
    """Сумма реферального бонуса на баланс для владельца с учётом персонального override."""
    if owner.referral_fixed_bonus_kopecks is not None:
        return int(owner.referral_fixed_bonus_kopecks)
    return rub_to_kopecks(int(settings.referral_fixed_first_payment_bonus_rub))


async def owner_already_rewarded_for_referee_payment(
    session: AsyncSession,
    *,
    owner_user_id: int,
    referee_user_id: int,
) -> bool:
    """Был ли уже ``notify_ref_pay`` для пары (реферер, реферируемый)."""
    stmt = (
        select(Task.id)
        .where(
            Task.user_id == int(owner_user_id),
            Task.referee_id == int(referee_user_id),
            Task.task_type == NOTIFY_REF_PAY,
        )
        .limit(1)
    )
    return (await session.scalar(stmt)) is not None


def compute_referral_bonus_days_for_owner(
    *,
    policy: str,
    paid_months: int,
    settings: Settings,
    is_first_referee_payment: bool,
) -> int:
    """Сколько бонусных дней начислить рефереру при оплате реферируемым."""
    normalized = normalize_referral_bonus_policy(policy)
    if normalized == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE:
        return 0
    if normalized == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT:
        if not is_first_referee_payment:
            return 0
        return int(REFERRAL_BONUS_FIXED_FIRST_PAYMENT_DAYS)

    per_month = int(settings.referral_bonus_days_per_paid_month)
    return per_month * int(paid_months)


def compute_referral_balance_bonus_kopecks_for_owner(
    *,
    policy: str,
    owner: User,
    settings: Settings,
    is_first_referee_payment: bool,
) -> int:
    """Сколько копеек зачислить на баланс реферера при оплате реферируемым."""
    if not referral_bonus_policy_is_balance(policy):
        return 0
    if not is_first_referee_payment:
        return 0
    return effective_referral_fixed_bonus_kopecks(owner, settings)
