from datetime import datetime
from typing import Literal

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


class TributeWebhookTestPayload(BaseModel):
    """Полезная нагрузка тестового webhook: только поля, которые читает сервис."""

    subscription_id: int = Field(
        ge=1,
        description="Tribute Subscription ID (часть ключа идемпотентности). Любое число.",
    )
    telegram_user_id: int = Field(
        ge=1,
        description="Telegram user id; должен совпадать с users.telegram_id в БД.",
    )
    expires_at: datetime = Field(
        description=(
            "Дата окончания периода в Tribute (ISO-8601 UTC, например 2026-06-08T20:00:00Z). "
            "Часть ключа идемпотентности — для нового платежа меняйте на свежую."
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


class TributeWebhookTestBody(BaseModel):
    """Тело для тестового webhook (без HMAC, защищён X-Telegram-Bot-Secret)."""

    name: Literal["new_subscription", "renewed_subscription", "cancelled_subscription"] = Field(
        default="new_subscription",
        description=(
            "Имя события: new/renewed_subscription — пишет платёж и продлевает подписку; "
            "cancelled_subscription — только лог, БД не меняется."
        ),
    )
    payload: TributeWebhookTestPayload
