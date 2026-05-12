from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TributeTariffsPublic(BaseModel):
    """Четыре ссылки на оплату тарифов (цифровые товары), только web.tribute.tg."""

    web_link_1m: str = Field(description="1 месяц")
    web_link_3m: str = Field(description="3 месяца")
    web_link_6m: str = Field(description="6 месяцев")
    web_link_1y: str = Field(description="1 год")


class TributeRecurringPayLinks(BaseModel):
    """Рекуррентная подписка Tribute: ссылка в Telegram и в браузере."""

    tg_link: str = Field(description="Оплата подписки из клиента Telegram (deep-link).")
    web_link: str = Field(description="Оплата подписки в браузере (web.tribute.tg).")


class TributePaymentsLinksResponse(BaseModel):
    """Ссылки для клиента: тарифы (разовые web) и рекуррентная подписка (tg + web).

    Каждый блок либо полностью задан, либо ``null``, если в env не хватает полей.
    """

    tariffs: TributeTariffsPublic | None = None
    recurring_pay: TributeRecurringPayLinks | None = None


class TributeWebhookAck(BaseModel):
    """Краткий ответ webhook (для Tribute главное HTTP 200; тело только для отладки)."""

    ok: bool = True
    event: str | None = None
    duplicate: bool = False


class TributeWebhookSubscriptionTestPayload(BaseModel):
    """Тест подписочного события: поля, которые читает сервис."""

    subscription_id: int = Field(
        ge=1,
        description="Tribute Subscription ID (внешний ключ в external_id для подписки).",
    )
    telegram_user_id: int = Field(
        ge=1,
        description="Telegram user id; должен совпадать с users.telegram_id в БД.",
    )
    expires_at: datetime = Field(
        description=(
            "Дата окончания периода в Tribute (ISO-8601 UTC). "
            "Входит в external_id вместе с subscription_id."
        ),
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

    purchase_id: int = Field(ge=1, description="Уникальный purchase_id Tribute (external_id dp:…).")
    product_id: int = Field(ge=1, description="Должен совпасть с одним из TRIBUTE_DIGITAL_PRODUCT_ID_* в env.")
    amount: int = Field(default=19900, ge=0, description="Сумма в минорных единицах.")
    telegram_user_id: int = Field(ge=1, description="Telegram user id в БД.")
    transaction_id: int = Field(default=1, ge=1)
    product_name: str = Field(default="Test digital product")
    currency: str = Field(default="rub")
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
