"""Поля баланса для staff read-моделей пользователя."""

from __future__ import annotations

from decimal import Decimal

from app.config import settings
from app.domain.balance.money import kopecks_to_rub
from app.infrastructure.persistence.models.user import User


def staff_user_balance_fields(user: User) -> dict[str, Decimal | int | None]:
    balance_rub = kopecks_to_rub(int(user.balance_kopecks or 0))
    referral_fixed_bonus_rub = (
        int(user.referral_fixed_bonus_kopecks) // 100
        if user.referral_fixed_bonus_kopecks is not None
        else None
    )
    return {
        "balance_rub": balance_rub,
        "referral_fixed_bonus_rub": referral_fixed_bonus_rub,
        "referral_fixed_bonus_rub_default": int(settings.referral_fixed_first_payment_bonus_rub),
    }
