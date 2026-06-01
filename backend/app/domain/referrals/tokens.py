"""Генерация и валидация реферального токена.

Токен — это часть deep-link Telegram-бота (``?start=<token>``); Telegram пропускает только
``[A-Za-z0-9_]`` длиной до 64 символов, поэтому здесь та же выборка алфавита и регулярного
выражения. Минимальная длина 4 — чтобы случайные коллизии при ручном вводе не были массовыми.
"""

from __future__ import annotations

import re
import secrets
import string
from typing import Literal

from app.domain.referrals.errors import ReferralTokenShapeError

CounterKind = Literal["clicks", "registrations", "payments"]

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,64}$")
_ALPHABET = string.ascii_letters + string.digits + "_"


def generate_referral_token(length: int = 12) -> str:
    """Случайный токен указанной длины (по умолчанию 12 символов)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def validate_token_shape(token: str) -> None:
    """Проверка формата; бросает :class:`ReferralTokenShapeError` (HTTP 422) при несоответствии."""
    if not TOKEN_PATTERN.fullmatch(token):
        raise ReferralTokenShapeError
