"""Генераторы идентификаторов пользователя: токен подписки и UUID для VLESS."""

from __future__ import annotations

import uuid as uuid_lib
from secrets import token_urlsafe

_SUBSCRIPTION_TOKEN_BYTES = 24


def new_subscription_token() -> str:
    """Случайный URL-safe токен подписки (24 байта).

    Используется как путь в ссылке на подписку: достаточно длинный, чтобы при утечке файла
    подписки доступ нельзя было подобрать перебором.
    """
    return token_urlsafe(_SUBSCRIPTION_TOKEN_BYTES)


def new_vless_uuid() -> str:
    """UUIDv4 для VLESS-клиента (раздаётся на все Xray-узлы при регистрации)."""
    return str(uuid_lib.uuid4())
