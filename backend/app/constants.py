"""Проектные константы по умолчанию (секреты и окружение-специфичное — в ``.env`` / ``Settings``)."""

from __future__ import annotations

# Безопасный максимум для PostgreSQL BIGINT (signed 64-bit). Используется как `le=` в Pydantic.
BIGINT_MAX = 9_223_372_036_854_775_807

# Имя бренда для UI, YAML подписки и деплинков (UTF-8).
BRAND_NAME = "🍃Подорожник VPN"
BRAND_NAME_ASCII = "Podorozhnik VPN"

# Длина пробного периода подписки после регистрации (календарных дней).
TRIAL_DAYS_AFTER_REGISTRATION = 14

# Срок жизни access-JWT (дни) — единый для портала и админ-API.
JWT_TOKEN_TTL_DAYS = 14

# --- Tribute: публичные ссылки на оплату (не секреты) ---
# Заполните здесь или задайте TRIBUTE_* в окружении — env перекрывает дефолты (см. ``app.config.Settings``).
TRIBUTE_TARIFF_WEB_LINK_1M: str = "https://web.tribute.tg/p/vRX"
TRIBUTE_TARIFF_WEB_LINK_3M: str = ""
TRIBUTE_TARIFF_WEB_LINK_6M: str = ""
TRIBUTE_TARIFF_WEB_LINK_1Y: str = ""

# Точные product_name из webhook new_digital_product (после .strip()) → срок; пустая строка — не сопоставлять.
TRIBUTE_DIGITAL_PRODUCT_NAME_1M: str = "Подорожник VPN | 1 месяц"
TRIBUTE_DIGITAL_PRODUCT_NAME_3M: str = ""
TRIBUTE_DIGITAL_PRODUCT_NAME_6M: str = ""
TRIBUTE_DIGITAL_PRODUCT_NAME_1Y: str = ""

TRIBUTE_RECURRING_PAY_TG_LINK: str = "https://t.me/tribute/app?startapp=sTWv"
TRIBUTE_RECURRING_PAY_WEB_LINK: str = "https://web.tribute.tg/s/TWv"
