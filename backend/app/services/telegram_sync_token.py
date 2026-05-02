"""Одноразовые токены привязки веб-аккаунта к Telegram (Redis)."""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

if TYPE_CHECKING:
    from redis import Redis

_KEY_PREFIX = "vpn:tg_web_link:"
# Одноразовый токен: Telegram → сайт (добавить email/пароль к учётке по telegram_id).
_SITE_CRED_PREFIX = "vpn:tg_site_cred:"
_TTL_SEC = 15 * 60
_TOKEN_LEN = 32
_TOKEN_ALPHABET = string.ascii_letters + string.digits + "_"


class TelegramSyncRedisError(RedisError):
    """Redis недоступен или ошибка протокола при работе с токеном синхронизации."""


def generate_sync_token_value() -> str:
    """Случайная часть для deep link (только символы, разрешённые Telegram в /start)."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


def sync_start_payload(token_value: str) -> str:
    """Значение параметра ?start= для бота (не длиннее 64 символов)."""
    return f"link_{token_value}"


def store_sync_token(redis: Redis, token_value: str, user_id: int) -> None:
    try:
        redis.setex(_KEY_PREFIX + token_value, _TTL_SEC, str(int(user_id)))
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def get_sync_token_user_id(redis: Redis, token_value: str) -> int | None:
    try:
        raw = redis.get(_KEY_PREFIX + token_value)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def delete_sync_token(redis: Redis, token_value: str) -> None:
    try:
        redis.delete(_KEY_PREFIX + token_value)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def store_site_cred_token(redis: Redis, token_value: str, user_id: int) -> None:
    """Связь одноразового токена (URL на сайт) с internal user_id."""
    try:
        redis.setex(_SITE_CRED_PREFIX + token_value, _TTL_SEC, str(int(user_id)))
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def get_site_cred_user_id(redis: Redis, token_value: str) -> int | None:
    try:
        raw = redis.get(_SITE_CRED_PREFIX + token_value)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def delete_site_cred_token(redis: Redis, token_value: str) -> None:
    try:
        redis.delete(_SITE_CRED_PREFIX + token_value)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
