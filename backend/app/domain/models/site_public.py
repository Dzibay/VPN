"""Публичные ссылки сайта (без авторизации)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublicProjectLegalInfo(BaseModel):
    """Плейсхолдеры для юридических документов SPA (из projects + brand.legal)."""

    service_name: str = Field(description="Название сервиса для текстов оферты и политик.")
    site_url: str | None = Field(default=None, description="Канонический origin SPA.")
    domain: str | None = Field(default=None, description="Основной домен проекта (host).")
    telegram_bot: str | None = Field(
        default=None,
        description="Username бота с @ для текстов документов.",
    )
    support_telegram: str | None = Field(
        default=None,
        description="Username поддержки с @; fallback на бота.",
    )
    support_email: str | None = Field(default=None, description="Email поддержки проекта.")
    operator_name: str | None = Field(default=None, description="ФИО оператора (brand.legal).")
    operator_inn: str | None = Field(default=None, description="ИНН оператора (brand.legal).")
    dispute_jurisdiction: str | None = Field(
        default=None,
        description="Подсудность (brand.legal.dispute_jurisdiction).",
    )
    effective_date: str | None = Field(
        default=None,
        description="Дата редакции документов (brand.legal.effective_date).",
    )
    trial_days_after_registration: int = Field(
        default=3,
        description="Длина тестового периода для новых пользователей (календарных дней).",
    )
    trial_extra_days_referral_registration: int = Field(
        default=2,
        description="Дополнительные дни триала при регистрации по реферальной ссылке друга.",
    )
    trial_days_with_referral: int = Field(
        default=5,
        description="Суммарный триал при регистрации по реферальной ссылке.",
    )
    trial_traffic_limit_gib: int = Field(
        default=20,
        description="Лимит трафика (GiB) для новых пользователей без оплат.",
    )


class PublicSiteLinksResponse(BaseModel):
    """GET /api/public/site-links — для страниц без JWT (например возврат после оплаты из бота)."""

    canonical_site_url: str | None = Field(
        default=None,
        description="Канонический origin SPA из SITE_ADDRESS (основной домен, без «/» в конце).",
    )
    telegram_bot_page_url: str | None = Field(
        default=None,
        description="https://t.me/{TELEGRAM_BOT_USERNAME}; null, если бот не настроен.",
    )
    support_telegram_url: str | None = Field(
        default=None,
        description="https://t.me/{SUPPORT_TELEGRAM_USERNAME}; null, если не задано.",
    )
    legal: PublicProjectLegalInfo | None = Field(
        default=None,
        description="Данные текущего проекта для юридических документов.",
    )


class IpBlockedStatusResponse(BaseModel):
    blocked: bool = Field(description="True, если IP клиента в списке blocked_ips")
