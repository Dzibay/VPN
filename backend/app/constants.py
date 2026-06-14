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

# --- Tribute: ссылки для GET …/payments/tribute-links — ``app/data/tribute_tariffs.json``; цены — ``yookassa_tariffs.json``. ---

# Точные product_name из webhook new_digital_product (после .strip()) → срок; пустая строка — не сопоставлять.
TRIBUTE_DIGITAL_PRODUCT_NAME_1M: str = "Старт (1 месяц)"
TRIBUTE_DIGITAL_PRODUCT_NAME_3M: str = "Оптимальный (3 месяца)"
TRIBUTE_DIGITAL_PRODUCT_NAME_6M: str = "Популярный (6 месяцев) 🔥"
TRIBUTE_DIGITAL_PRODUCT_NAME_1Y: str = "Максимальная выгода (1 год) 💎"

# Комиссия Tribute с валовой суммы (10%). В webhook нет income_amount — считаем сами.
TRIBUTE_PSP_FEE_RATE = "0.10"

# --- Реферальные бонусы: политики users.referral_bonus_policy ---

REFERRAL_BONUS_POLICY_DEFAULT = "default"
REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT = "fixed_first_payment_instant"
REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE = "fixed_first_payment_balance"
REFERRAL_BONUS_POLICIES = frozenset(
    {
        REFERRAL_BONUS_POLICY_DEFAULT,
        REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT,
        REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_BALANCE,
    },
)
# Фиксированный бонус (дней) при первой оплате каждого приведённого друга (политика fixed_first_payment_instant).
REFERRAL_BONUS_FIXED_FIRST_PAYMENT_DAYS = 20

# --- Баланс пользователя: виды операций в user_balance_ledger ---

USER_BALANCE_LEDGER_KIND_REFERRAL_FIRST_PAYMENT = "referral_first_payment"


