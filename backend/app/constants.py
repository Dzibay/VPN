"""Проектные константы, не зависящие от окружения (переменные приложения — в ``app.config``)."""

from __future__ import annotations

# Безопасный максимум для PostgreSQL BIGINT (signed 64-bit). Используется как `le=` в Pydantic.
BIGINT_MAX = 9_223_372_036_854_775_807

# Имя бренда для UI и подписочных деплинков (Cyrillic).
BRAND_NAME = "Подорожник VPN"

# ASCII-вариант для HTTP-заголовков подписки (`profile-title` и т.п.):
# часть старых клиентов читает заголовок как ASCII и ломается на UTF-8.
BRAND_NAME_ASCII = "Podorozhnik VPN"

# Длина пробного периода подписки после регистрации (календарных дней).
TRIAL_DAYS_AFTER_REGISTRATION = 14

# Срок жизни access-JWT (дни) — единый для портала и админ-API.
JWT_TOKEN_TTL_DAYS = 14
