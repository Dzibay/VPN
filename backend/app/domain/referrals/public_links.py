"""Публичные URL для одной реферальной ссылки: site-redirect и Telegram deep-link.

URL строятся по проекту ссылки (``referral_links.project_id``), а не только по env.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from app.domain.public_urls import _telegram_bot_username_clean, public_spa_base_url
from app.domain.tenant.project_context import ProjectContext
from app.infrastructure.persistence.models.referral_link import ReferralLink


def referral_site_register_url(
    settings: object,
    token: str,
    *,
    project: ProjectContext | None = None,
) -> str | None:
    """Главная SPA с GET-параметром ``?ref=<token>`` (запоминается в localStorage)."""
    base = public_spa_base_url(settings, project)
    if not base:
        return None
    return f"{base}/?ref={quote(token, safe='')}"


def referral_telegram_deep_link(
    settings: object,
    token: str,
    *,
    project: ProjectContext | None = None,
) -> str | None:
    """``https://t.me/{bot}?start=<token>`` для запуска бота проекта."""
    bot = _telegram_bot_username_clean(settings, project)
    if not bot:
        return None
    return f"https://t.me/{bot}?start={quote(token, safe='')}"


def referral_link_to_response(
    link: ReferralLink,
    settings: object,
    *,
    project: ProjectContext | None = None,
    revenue_net: Decimal | None = None,
):
    """Сборка ``ReferralLinkOut`` с подставленными URL (для list/me-эндпоинтов)."""
    from app.domain.models.referral_links import ReferralLinkOut, ReferralLinkRead

    core = ReferralLinkRead.model_validate(link)
    return ReferralLinkOut(
        **core.model_dump(),
        revenue_net=revenue_net if revenue_net is not None else Decimal("0"),
        site_entry_url=referral_site_register_url(settings, link.token, project=project),
        telegram_deep_link=referral_telegram_deep_link(settings, link.token, project=project),
    )
