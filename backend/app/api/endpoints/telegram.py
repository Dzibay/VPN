"""Эндпоинты для бэкенда Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from fastapi import APIRouter, Depends

from app.api.deps import require_telegram_bot_api_secret
from app.core.config import settings
from app.domain.subscription_public_base import prefer_https_subscription_public_base
from app.schemas.account import (
    TelegramSubscriptionOpenClientsResponse,
    build_subscription_open_client_items,
)

router = APIRouter(prefix="/telegram", tags=["public"])


@router.get(
    "/subscription-open-clients",
    response_model=TelegramSubscriptionOpenClientsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Список VPN-клиентов для кнопок «Подключить» (тот же источник, что /api/auth/me; секрет бота)",
)
async def subscription_open_clients() -> TelegramSubscriptionOpenClientsResponse:
    raw = (settings.subscription_public_base_url or "").strip().rstrip("/")
    base = prefer_https_subscription_public_base(raw) if raw else ""
    return TelegramSubscriptionOpenClientsResponse(
        clients=build_subscription_open_client_items(),
        public_base_url=base or None,
    )
