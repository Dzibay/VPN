"""Утилита для подписи webhook-тела Tribute (для ручного теста через Swagger).

Запуск:

    python scripts/sign_tribute_webhook.py

Печатает:

- ровно тот JSON, что нужно вставить в Swagger как тело запроса (`raw body`);
- значение заголовка ``trbt-signature``.

Если меняешь BODY — повторно запусти скрипт и обнови оба значения в Swagger.
"""

from __future__ import annotations

import hashlib
import hmac

API_KEY = "8be3d162-4360-4e16-a479-dd2c9790"

BODY = (
    '{"name":"new_subscription",'
    '"created_at":"2026-05-08T20:00:00Z",'
    '"sent_at":"2026-05-08T20:00:00.123Z",'
    '"payload":{'
    '"subscription_name":"VPN",'
    '"subscription_id":1644,'
    '"period_id":1547,'
    '"period":"monthly",'
    '"type":"regular",'
    '"price":19900,'
    '"amount":17000,'
    '"currency":"rub",'
    '"user_id":31326,'
    '"trb_user_id":"T-31326",'
    '"telegram_user_id":123456789,'
    '"telegram_username":"test_user",'
    '"channel_id":614,'
    '"channel_name":"vpn",'
    '"expires_at":"2026-06-08T20:00:00Z"'
    "}}"
)


def main() -> None:
    raw = BODY.encode("utf-8")
    sig = hmac.new(API_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    print("=== request body (вставить в Swagger «как есть») ===")
    print(BODY)
    print()
    print("=== header trbt-signature ===")
    print(sig)


if __name__ == "__main__":
    main()
