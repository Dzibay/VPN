"""Индивидуальные политики реферальных бонусов (``users.referral_bonus_policy``)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.constants import (
    REFERRAL_BONUS_FIXED_FIRST_PAYMENT_DAYS,
    REFERRAL_BONUS_POLICIES,
    REFERRAL_BONUS_POLICY_DEFAULT,
    REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT,
)
from app.domain.tasks.notification_task_types import NOTIFY_REF_PAY
from app.infrastructure.persistence.models.task import Task


def normalize_referral_bonus_policy(raw: str | None) -> str:
    policy = (raw or REFERRAL_BONUS_POLICY_DEFAULT).strip()
    if policy not in REFERRAL_BONUS_POLICIES:
        return REFERRAL_BONUS_POLICY_DEFAULT
    return policy


def referral_bonus_applies_immediately(policy: str) -> bool:
    return policy == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT


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
    if normalized == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT:
        if not is_first_referee_payment:
            return 0
        return int(REFERRAL_BONUS_FIXED_FIRST_PAYMENT_DAYS)

    per_month = int(settings.referral_bonus_days_per_paid_month)
    return per_month * int(paid_months)
