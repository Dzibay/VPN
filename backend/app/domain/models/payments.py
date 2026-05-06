from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import BIGINT_MAX


class TelegramPaymentCreateBody(BaseModel):
    """Создание строки платежа со статусом pending (бот)."""

    telegram_id: int = Field(
        ge=1,
        le=BIGINT_MAX,
        description="Telegram user id (Bot API); владелец платежа в users.",
    )
    amount: Decimal = Field(ge=0, description="Сумма (NUMERIC 14,2 в БД).")
    months: int = Field(ge=1, description="Число месяцев подписки по этой оплате.")


class TelegramPaymentSetStatusBody(BaseModel):
    """Завершение платежа: только из pending в completed или failed."""

    status: Literal["completed", "failed"]


class TelegramPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: Decimal
    months: int
    status: str
    created_at: datetime
