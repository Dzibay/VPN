"""Сборка публичных URL для бренда: страница SPA и страница бота в Telegram.

Модуль не зависит от модели подписок и реферальных ссылок — его можно использовать
из любых сервисов, которые хотят отдать пользователю «человеческую» ссылку. Источник
адресов — переменные окружения (``SITE_ADDRESS``, ``TELEGRAM_BOT_USERNAME``).
"""

from __future__ import annotations

from app.domain.subscription.public_base import site_address_to_public_origin
from app.domain.tenant.project_context import get_current_project


def _telegram_bot_username_clean(settings: object) -> str:
    """Имя бота без ведущего ``@`` и пробелов; пусто, если не задано."""
    return (getattr(settings, "telegram_bot_username", None) or "").strip().lstrip("@")


def telegram_bot_public_page_url(settings: object) -> str | None:
    """``https://t.me/{username}`` без deep-link (используется в личном кабинете и в /me)."""
    bot = _telegram_bot_username_clean(settings)
    if not bot:
        return None
    return f"https://t.me/{bot}"


def _support_telegram_username_clean(settings: object) -> str:
    """Username аккаунта поддержки без ``@``."""
    return (getattr(settings, "support_telegram_username", None) or "").strip().lstrip("@")


def support_telegram_public_url(settings: object) -> str | None:
    """``https://t.me/{username}`` для чата поддержки (не бот)."""
    user = _support_telegram_username_clean(settings)
    if not user:
        return None
    return f"https://t.me/{user}"


def public_spa_base_url(settings: object) -> str | None:
    """Публичный origin SPA из ``SITE_ADDRESS`` (полный URL или ``host[:port]``).

    Нормализует http→https для публичных хостов; для локальной сети остаётся http (см.
    :mod:`app.domain.subscription.public_base`).
    """
    project = get_current_project()
    if project is not None and project.primary_domain:
        from_site = site_address_to_public_origin(project.primary_domain)
        if from_site:
            return from_site
    from_site = site_address_to_public_origin(getattr(settings, "site_address", None) or "")
    return from_site or None
