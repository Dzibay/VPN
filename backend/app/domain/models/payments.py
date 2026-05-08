from typing import Any

from pydantic import BaseModel, Field


class TributeSubscriptionPublic(BaseModel):
    """Публичная карточка подписки Tribute (одна ссылка для tg и web)."""

    tg_link: str
    web_link: str


class TributeSubscriptionResponse(BaseModel):
    """Ответ кабинета и бота: либо настроенная подписка, либо null."""

    subscription: TributeSubscriptionPublic | None = None


class TributeWebhookAck(BaseModel):
    """Краткий ответ webhook (для Tribute главное HTTP 200; тело только для отладки)."""

    ok: bool = True
    event: str | None = None
    duplicate: bool = False


class TributeWebhookTestBody(BaseModel):
    """Тело для тестового webhook-эндпоинта без HMAC (защищён бот-секретом).

    Структура повторяет реальный webhook Tribute: ``name`` + произвольный ``payload``.
    Поля ``payload`` зависят от события, см. сервис ``tribute_service`` и схему Tribute.
    """

    name: str = Field(
        description=(
            "Имя события Tribute: new_subscription | renewed_subscription | cancelled_subscription. "
            "Любое другое значение → 200 без изменений."
        ),
        examples=["new_subscription"],
    )
    payload: dict[str, Any] = Field(
        description=(
            "Полезная нагрузка события. Минимум для new/renewed_subscription: subscription_id, period_id, "
            "period (monthly|quarterly|yearly), price (минор. ед.), amount, currency, expires_at (ISO-8601), "
            "telegram_user_id (должен совпадать с users.telegram_id). Поле type=gift — пропускаем платёж."
        ),
        examples=[{
            "subscription_name": "VPN",
            "subscription_id": 1644,
            "period_id": 1547,
            "period": "monthly",
            "type": "regular",
            "price": 19900,
            "amount": 17000,
            "currency": "rub",
            "user_id": 31326,
            "trb_user_id": "T-31326",
            "telegram_user_id": 123456789,
            "telegram_username": "test_user",
            "channel_id": 614,
            "channel_name": "vpn",
            "expires_at": "2026-06-08T20:00:00Z",
        }],
    )
