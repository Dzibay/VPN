"""Конвертация рублей ↔ копейки для баланса пользователя."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def rub_to_kopecks(rub: int) -> int:
    if rub < 1:
        raise ValueError("rub must be >= 1")
    return int(rub) * 100


def kopecks_to_rub(kopecks: int) -> Decimal:
    return (Decimal(int(kopecks)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
