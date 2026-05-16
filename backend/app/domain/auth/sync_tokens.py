"""Одноразовые токены в Redis для двух Telegram-сценариев привязки.

Поддерживается два независимых неймспейса:

* ``vpn:tg_sync:{value}`` — пользователь жмёт «Привязать Telegram» в личном кабинете,
  получает deep link на бота: бот по своей стороне вызывает API и обменивает токен на
  ``user_id``.
* ``vpn:tg_sync_pending:{user_id}`` — обратный индекс: пока токен жив, повторный запрос
  из кабинета возвращает ту же ссылку (TTL 15 мин, продлевается при повторном нажатии).
* ``vpn:tg_site_cred:{value}`` — пользователь нажал «Привязать аккаунт сайта» внутри бота,
  бот выдал ему ссылку на сайт с одноразовым токеном; на сайте по нему резолвится
  ``user_id`` и собирается форма ввода email и пароля.

Все операции бросают :class:`TelegramSyncRedisError` при сетевых ошибках Redis (вызывающий
код переводит её в HTTP 503).
"""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError

if TYPE_CHECKING:
    from redis import Redis

_TOKEN_ALPHABET = string.ascii_letters + string.digits + "_"
_TOKEN_LEN = 32
_TTL_SEC = 900
_KEY_PREFIX_TELEGRAM_LINK = "vpn:tg_sync:"
_KEY_PREFIX_TELEGRAM_LINK_USER = "vpn:tg_sync_pending:"
_KEY_PREFIX_SITE_CRED = "vpn:tg_site_cred:"


class TelegramSyncRedisError(Exception):
    """Ошибка записи или чтения одноразового токена Telegram в Redis."""


def generate_sync_token_value() -> str:
    """Случайная часть для deep link (только символы, разрешённые Telegram в ``/start``)."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


def sync_start_payload(token_value: str) -> str:
    """Значение параметра ``?start=`` для бота (не длиннее 64 символов)."""
    return f"link_{token_value}"


def _setex_user_mapping(redis: Redis, full_key: str, user_id: int) -> None:
    try:
        redis.setex(full_key, _TTL_SEC, str(int(user_id)))
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def _setex_str_mapping(redis: Redis, full_key: str, value: str) -> None:
    try:
        redis.setex(full_key, _TTL_SEC, value)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def _get_mapping_user_id(redis: Redis, full_key: str) -> int | None:
    try:
        raw = redis.get(full_key)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
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
        raise TelegramSyncRedisError(str(e)) from e


def store_telegram_link_token(redis: Redis, token_value: str, user_id: int) -> None:
    """Запомнить связку ``token → user_id`` для deep link на бота из личного кабинета."""
    uid = int(user_id)
    _setex_user_mapping(redis, _KEY_PREFIX_TELEGRAM_LINK + token_value, uid)
    _setex_str_mapping(redis, _KEY_PREFIX_TELEGRAM_LINK_USER + str(uid), token_value)


def _get_pending_telegram_link_token(redis: Redis, user_id: int) -> str | None:
    """Активный токен привязки для пользователя (None — нет или истёк)."""
    uid = int(user_id)
    pending_key = _KEY_PREFIX_TELEGRAM_LINK_USER + str(uid)
    try:
        raw = redis.get(pending_key)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
    if raw is None:
        return None
    token = raw.decode() if isinstance(raw, bytes) else str(raw)
    if not token:
        return None
    mapped_uid = get_telegram_link_user_id(redis, token)
    if mapped_uid != uid:
        _delete_mapping(redis, pending_key)
        return None
    return token


def get_or_issue_telegram_link_token(redis: Redis, user_id: int) -> str:
    """Вернуть действующий токен или создать новый (TTL обновляется при повторном запросе)."""
    existing = _get_pending_telegram_link_token(redis, user_id)
    if existing:
        store_telegram_link_token(redis, existing, user_id)
        return existing
    token_val = generate_sync_token_value()
    store_telegram_link_token(redis, token_val, user_id)
    return token_val


def get_telegram_link_user_id(redis: Redis, token_value: str) -> int | None:
    """Получить ``user_id`` по токену из ``/start link_…`` (None — токен истёк или неизвестен)."""
    return _get_mapping_user_id(redis, _KEY_PREFIX_TELEGRAM_LINK + token_value)


def delete_telegram_link_token(redis: Redis, token_value: str) -> None:
    """Удалить токен после успешной привязки Telegram (или ручной отмены)."""
    uid = get_telegram_link_user_id(redis, token_value)
    _delete_mapping(redis, _KEY_PREFIX_TELEGRAM_LINK + token_value)
    if uid is not None:
        _delete_mapping(redis, _KEY_PREFIX_TELEGRAM_LINK_USER + str(uid))


def store_site_cred_token(redis: Redis, token_value: str, user_id: int) -> None:
    """Запомнить связку ``token → user_id`` для одноразовой ссылки на сайт из бота."""
    _setex_user_mapping(redis, _KEY_PREFIX_SITE_CRED + token_value, user_id)


def get_site_cred_user_id(redis: Redis, token_value: str) -> int | None:
    """Получить ``user_id`` по одноразовому токену сайта (None — токен истёк или неизвестен)."""
    return _get_mapping_user_id(redis, _KEY_PREFIX_SITE_CRED + token_value)


def delete_site_cred_token(redis: Redis, token_value: str) -> None:
    """Удалить site-токен после успешной привязки email (или ручной отмены)."""
    _delete_mapping(redis, _KEY_PREFIX_SITE_CRED + token_value)


def normalize_site_token(raw: str) -> str:
    """Нормализованный токен из URL: убирает пробелы (часть мессенджеров добавляет их при копировании)."""
    return str(raw).strip().replace(" ", "")


def resolve_site_cred_user_id(redis: object, raw_token: str) -> tuple[int, str]:
    """Резолв одноразового site-cred-токена → ``(user_id, нормализованный токен)``.

    Бросает соответствующий подкласс ``AppError`` (400 — некорректный, 404 — истёк,
    503 — Redis недоступен); нормализованный токен возвращается, чтобы повторно не делать
    ``strip`` на стороне вызова.
    """
    key_part = normalize_site_token(raw_token)
    if len(key_part) < 4:
        raise BadRequestError("Некорректный токен")
    try:
        uid = get_site_cred_user_id(redis, key_part)
    except TelegramSyncRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None
    if uid is None:
        raise NotFoundError(
            "Ссылка недействительна или истекла. Запросите новую в боте.",
        )
    return uid, key_part
