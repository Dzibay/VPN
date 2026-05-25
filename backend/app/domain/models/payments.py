from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TributePaymentOptionKind = Literal["single", "recurring"]


class TributePaymentOptionItem(BaseModel):
    """Один вариант оплаты Tribute: разовый тариф или рекуррентная подписка."""

    months: int | None = Field(
        default=None,
        description="Срок разовой покупки в месяцах; для подписки — null.",
    )
    price: int | None = Field(
        default=None,
        description=(
            "Цена в минорных единицах (разовый тариф); null если в конфиге 0 / не задана, для подписки — null."
        ),
    )
    tg_link: str | None = Field(
        default=None,
        description="Deep-link в Telegram; для разовых тарифов всегда null.",
    )
    web_link: str = Field(description="Оплата в браузере (web.tribute.tg).")
    name: str = Field(description="Подпись для кнопки или списка.")
    type: TributePaymentOptionKind = Field(description="single — разовая оплата; recurring — подписка.")


class TributePaymentsLinksResponse(BaseModel):
    """Все доступные способы оплаты Tribute в одном списке (порядок: разовые по сроку, затем подписка)."""

    tariffs: list[TributePaymentOptionItem] = Field(
        default_factory=list,
        description="Только варианты с непустыми ссылками в настройках; длина не фиксирована.",
    )


class PaymentWebhookAck(BaseModel):
    """Краткий ответ webhook провайдера (HTTP 200; тело для отладки)."""

    ok: bool = True
    event: str | None = None
    duplicate: bool = False
    payment_id: int | None = None
    fulfilled: bool = False
    skip_reason: str | None = None


# Обратная совместимость импортов и OpenAPI
TributeWebhookAck = PaymentWebhookAck


class SitePaymentTariffItem(BaseModel):
    """Разовый тариф для оплаты на сайте (ЮKassa)."""

    months: int = Field(ge=1, le=120, description="Срок в месяцах.")
    price: int = Field(ge=1, description="Цена в рублях (целое число).")
    name: str = Field(description="Подпись для UI.")


class SitePaymentTariffsResponse(BaseModel):
    tariffs: list[SitePaymentTariffItem] = Field(default_factory=list)


class YookassaCheckoutBody(BaseModel):
    months: int = Field(ge=1, le=120, description="Срок из yookassa_tariffs.json")


class TelegramYookassaCheckoutBody(BaseModel):
    """Запрос бота: POST /api/telegram/payments/yookassa/checkout (X-Telegram-Bot-Secret)."""

    telegram_id: int = Field(ge=1, description="Telegram user id (Bot API); должен быть в users.telegram_id.")
    months: int = Field(
        ge=1,
        le=120,
        description="Срок разовой оплаты в месяцах; цена берётся из yookassa_tariffs.json (не из запроса).",
    )


class YookassaCheckoutResponse(BaseModel):
    confirmation_url: str = Field(description="URL редиректа на оплату ЮKassa")
    yookassa_payment_id: str = Field(description="Идентификатор платежа в ЮKassa")


class TributeWebhookSubscriptionTestPayload(BaseModel):
    """Тест подписочного события: поля, которые читает сервис."""

    subscription_id: int = Field(
        ge=1,
        description="Tribute Subscription ID (в payload webhook подписки).",
    )
    telegram_user_id: int = Field(
        ge=1,
        description="Telegram user id; должен совпадать с users.telegram_id в БД.",
    )
    expires_at: datetime = Field(
        description="Дата окончания периода в Tribute (ISO-8601 UTC); сохраняется в provider_webhook.",
    )
    period: Literal["monthly", "quarterly", "yearly"] = Field(
        default="monthly",
        description="Период подписки: 1 / 3 / 12 месяцев (× 31 день к users.subscription_until).",
    )
    price: int = Field(
        default=19900,
        ge=0,
        description="Цена в минорных единицах (копейки). Делится на 100 → payments.amount.",
    )
    type: Literal["regular", "gift", "trial"] | None = Field(
        default=None,
        description="Тип подписки. type=gift пропускается (платежа нет).",
    )


class TributeWebhookDigitalTestPayload(BaseModel):
    """Тест ``new_digital_product`` (разовая покупка)."""

    purchase_id: int = Field(ge=1, description="Уникальный purchase_id Tribute (дедупликация в provider_webhook).")
    product_id: int = Field(ge=1, description="ID цифрового товара в Tribute.")
    amount: int = Field(default=19900, ge=0, description="Сумма в минорных единицах.")
    telegram_user_id: int = Field(ge=1, description="Telegram user id в БД.")
    transaction_id: int = Field(default=1, ge=1)
    product_name: str = Field(default="Test digital product")
    currency: str = Field(default="rub")
    months: int = Field(default=1, ge=1, le=120, description="Срок в месяцах (как в webhook).")
    purchase_created_at: datetime | None = Field(
        default=None,
        description="По умолчанию — текущее время (если клиент не передал).",
    )


class TributeWebhookSubscriptionTestBody(BaseModel):
    """Тест webhook подписки (без HMAC, защищён X-Telegram-Bot-Secret)."""

    name: Literal["new_subscription", "renewed_subscription", "cancelled_subscription"] = Field(
        default="new_subscription",
        description=(
            "new/renewed_subscription — пишет платёж (payment_kind=subscription) и продлевает доступ; "
            "cancelled_subscription — только лог."
        ),
    )
    payload: TributeWebhookSubscriptionTestPayload


class TributeWebhookDigitalTestBody(BaseModel):
    """Тест webhook цифрового товара."""

    name: Literal["new_digital_product"] = "new_digital_product"
    payload: TributeWebhookDigitalTestPayload


TributeWebhookTestBody = TributeWebhookSubscriptionTestBody | TributeWebhookDigitalTestBody
