"""Одноразовые токены подтверждения email в Redis.

* ``vpn:email_verify:{token}`` → ``user_id``
* ``vpn:email_verify_user:{user_id}`` → текущий ``token`` (инвалидация при повторной отправке)
"""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

if TYPE_CHECKING:
    from redis import Redis

_TOKEN_ALPHABET = string.ascii_letters + string.digits
_TOKEN_LEN = 48
_KEY_PREFIX = "vpn:email_verify:"
_KEY_PREFIX_USER = "vpn:email_verify_user:"
_KEY_PREFIX_RESEND_COOLDOWN = "vpn:email_verify_resend:"


class EmailVerifyRedisError(Exception):
    """Ошибка записи или чтения токена подтверждения email в Redis."""


def generate_email_verify_token_value() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


def _setex_user_mapping(redis: Redis, full_key: str, user_id: int, ttl_sec: int) -> None:
    try:
        redis.setex(full_key, ttl_sec, str(int(user_id)))
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e


def _get_mapping_user_id(redis: Redis, full_key: str) -> int | None:
    try:
        raw = redis.get(full_key)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _delete_mapping(redis: Redis, full_key: str) -> None:
    try:
        redis.delete(full_key)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e


def store_email_verify_token(redis: Redis, user_id: int, *, ttl_sec: int) -> str:
    """Сохранить новый токен; предыдущий для этого user_id удаляется."""
    token = generate_email_verify_token_value()
    uid = int(user_id)
    user_key = f"{_KEY_PREFIX_USER}{uid}"
    try:
        old_token = redis.get(user_key)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
    if old_token:
        old_s = old_token.decode("utf-8") if isinstance(old_token, bytes) else str(old_token)
        _delete_mapping(redis, f"{_KEY_PREFIX}{old_s}")
    _setex_user_mapping(redis, f"{_KEY_PREFIX}{token}", uid, ttl_sec)
    try:
        redis.setex(user_key, ttl_sec, token)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
    return token


def resolve_email_verify_user_id(redis: Redis, token: str) -> int | None:
    return _get_mapping_user_id(redis, f"{_KEY_PREFIX}{token}")


def delete_email_verify_token(redis: Redis, token: str, user_id: int | None = None) -> None:
    _delete_mapping(redis, f"{_KEY_PREFIX}{token}")
    if user_id is not None:
        _delete_mapping(redis, f"{_KEY_PREFIX_USER}{int(user_id)}")


def purge_email_verify_for_user(redis: Redis, user_id: int) -> None:
    """Удалить все Redis-ключи подтверждения email для пользователя (перед удалением из БД)."""
    uid = int(user_id)
    user_key = f"{_KEY_PREFIX_USER}{uid}"
    try:
        raw = redis.get(user_key)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
    if raw:
        token = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        if token:
            _delete_mapping(redis, f"{_KEY_PREFIX}{token}")
    _delete_mapping(redis, user_key)
    _delete_mapping(redis, f"{_KEY_PREFIX_RESEND_COOLDOWN}{uid}")


def resend_cooldown_remaining_sec(redis: Redis, user_id: int) -> int | None:
    """Секунды до следующей повторной отправки; ``None``, если лимит не активен."""
    key = f"{_KEY_PREFIX_RESEND_COOLDOWN}{int(user_id)}"
    try:
        ttl = redis.ttl(key)
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
    if ttl is None or int(ttl) < 1:
        return None
    return int(ttl)


def touch_resend_cooldown(redis: Redis, user_id: int, *, ttl_sec: int) -> None:
    key = f"{_KEY_PREFIX_RESEND_COOLDOWN}{int(user_id)}"
    try:
        redis.setex(key, int(ttl_sec), "1")
    except RedisError as e:
        raise EmailVerifyRedisError(str(e)) from e
