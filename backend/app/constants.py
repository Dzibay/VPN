"""Проектные константы по умолчанию (секреты и окружение-специфичное — в ``.env`` / ``Settings``)."""

from __future__ import annotations

# Безопасный максимум для PostgreSQL BIGINT (signed 64-bit). Используется как `le=` в Pydantic.
BIGINT_MAX = 9_223_372_036_854_775_807

# Имя бренда для UI, YAML подписки и деплинков (UTF-8).
BRAND_NAME = "🍃 Подорожник VPN"

# Длина пробного периода подписки после регистрации (календарных дней).
TRIAL_DAYS_AFTER_REGISTRATION = 3
TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION = 2

# Лимит накопленного трафика (up+down по всем узлам) для клиентов без записей в payments.
TRIAL_TRAFFIC_LIMIT_GIB = 20

# Срок жизни access-JWT (дни) — единый для портала и админ-API.
JWT_TOKEN_TTL_DAYS = 14

# --- Tribute: тарифы для GET …/payments/tribute-links — файл ``app/data/tribute_tariffs.json`` (редактируйте его). ---

# Точные product_name из webhook new_digital_product (после .strip()) → срок; пустая строка — не сопоставлять.
TRIBUTE_DIGITAL_PRODUCT_NAME_1M: str = "Старт (1 месяц)"
TRIBUTE_DIGITAL_PRODUCT_NAME_3M: str = "Оптимальный (3 месяца)"
TRIBUTE_DIGITAL_PRODUCT_NAME_6M: str = "Популярный (6 месяцев) 🔥"
TRIBUTE_DIGITAL_PRODUCT_NAME_1Y: str = "Максимальная выгода (1 год) 💎"


