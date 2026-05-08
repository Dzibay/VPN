from pydantic import BaseModel


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
