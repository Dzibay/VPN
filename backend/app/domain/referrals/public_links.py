"""Публичные URL для одной реферальной ссылки: site-redirect и Telegram deep-link.

Использует :mod:`app.domain.public_urls` для базы (host SPA и страница бота). Генерируемые
URL встраиваются в ответ административного API и в личный кабинет клиента.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from app.domain.public_urls import _telegram_bot_username_clean, public_spa_base_url
from app.infrastructure.persistence.models.referral_link import ReferralLink


def referral_site_register_url(settings: object, token: str) -> str | None:
    """Главная SPA с GET-параметром ``?ref=<token>`` (запоминается в localStorage)."""
    base = public_spa_base_url(settings)
    if not base:
        return None
    return f"{base}/?ref={quote(token, safe='')}"


def referral_telegram_deep_link(settings: object, token: str) -> str | None:
    """``https://t.me/{TELEGRAM_BOT_USERNAME}?start=<token>`` для запуска бота."""
    bot = _telegram_bot_username_clean(settings)
    if not bot:
        return None
    return f"https://t.me/{bot}?start={quote(token, safe='')}"


def referral_link_to_response(
    link: ReferralLink,
    settings: object,
    *,
    revenue_net: Decimal | None = None,
):
    """Сборка ``ReferralLinkOut`` с подставленными URL (для list/me-эндпоинтов)."""
    from app.domain.models.referral_links import ReferralLinkOut, ReferralLinkRead

    core = ReferralLinkRead.model_validate(link)
    return ReferralLinkOut(
        **core.model_dump(),
        revenue_net=revenue_net if revenue_net is not None else Decimal("0"),
        site_entry_url=referral_site_register_url(settings, link.token),
        telegram_deep_link=referral_telegram_deep_link(settings, link.token),
    )
