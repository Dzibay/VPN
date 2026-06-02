"""Бонусные дни за своевременную (досрочную) оплату подписки."""

from __future__ import annotations

from datetime import date

MAX_EARLY_PAYMENT_BONUS_DAYS = 3


def compute_early_payment_bonus_days(
    subscription_until: date | None,
    payment_date: date,
    *,
    max_bonus: int = MAX_EARLY_PAYMENT_BONUS_DAYS,
) -> int:
    """Дни бонуса при оплате до окончания текущей подписки (календарь Москвы).

    ``subscription_until`` — последний день доступа до продления.
    ``payment_date`` — календарный день оплаты (Москва).

    За 3+ календарных дня до окончания — ``max_bonus`` (по умолчанию 3),
    за 2 — 2, за 1 — 1, в день окончания и позже — 0.
    """
    if subscription_until is None or max_bonus < 1:
        return 0
    days_before = (subscription_until - payment_date).days
    if days_before <= 0:
        return 0
    return min(days_before, max_bonus)
