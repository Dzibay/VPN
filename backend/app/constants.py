"""Проектные константы, не зависящие от окружения (переменные приложения — в ``app.config``)."""

from __future__ import annotations

# Безопасный максимум для PostgreSQL BIGINT (signed 64-bit). Используется как `le=` в Pydantic.
BIGINT_MAX = 9_223_372_036_854_775_807

# Имя бренда для UI, YAML подписки и деплинков (UTF-8).
BRAND_NAME = "🍃Подорожник VPN"

# Только latin-1/ASCII: значения HTTP-заголовков (например `profile-title`) в Starlette
# кодируются в latin-1 — эмодзи и прочий не‑latin-1 здесь дадут UnicodeEncodeError.
BRAND_NAME_ASCII = "Podorozhnik VPN"

# Длина пробного периода подписки после регистрации (календарных дней).
TRIAL_DAYS_AFTER_REGISTRATION = 14

# Срок жизни access-JWT (дни) — единый для портала и админ-API.
JWT_TOKEN_TTL_DAYS = 14
