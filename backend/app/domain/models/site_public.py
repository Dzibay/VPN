"""Публичные ссылки сайта (без авторизации)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublicSiteLinksResponse(BaseModel):
    """GET /api/public/site-links — для страниц без JWT (например возврат после оплаты из бота)."""

    telegram_bot_page_url: str | None = Field(
        default=None,
        description="https://t.me/{TELEGRAM_BOT_USERNAME}; null, если бот не настроен.",
    )
    support_telegram_url: str | None = Field(
        default=None,
        description="https://t.me/{SUPPORT_TELEGRAM_USERNAME}; null, если не задано.",
    )
