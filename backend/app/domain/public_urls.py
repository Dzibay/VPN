"""Сборка публичных URL для бренда: страница SPA и страница бота в Telegram.

Приоритет источников: явный ``ProjectContext`` → текущий проект запроса (Host /
``X-Admin-Project``) → legacy env (``SITE_ADDRESS``, ``TELEGRAM_BOT_USERNAME``).
"""

from __future__ import annotations

from app.domain.subscription.public_base import site_address_to_public_origin
from app.domain.tenant.project_context import ProjectContext, get_current_project


def _resolve_project(project: ProjectContext | None = None) -> ProjectContext | None:
    if project is not None:
        return project
    return get_current_project()


def _telegram_bot_username_clean(
    settings: object,
    project: ProjectContext | None = None,
) -> str:
    """Имя бота без ведущего ``@``; пусто, если не задано."""
    ctx = _resolve_project(project)
    if ctx is not None and ctx.telegram_bot_username:
        return str(ctx.telegram_bot_username).strip().lstrip("@")
    return (getattr(settings, "telegram_bot_username", None) or "").strip().lstrip("@")


def telegram_bot_public_page_url(
    settings: object,
    project: ProjectContext | None = None,
) -> str | None:
    """``https://t.me/{username}`` без deep-link (личный кабинет, /me)."""
    bot = _telegram_bot_username_clean(settings, project)
    if not bot:
        return None
    return f"https://t.me/{bot}"


def _support_telegram_username_clean(
    settings: object,
    project: ProjectContext | None = None,
) -> str:
    ctx = _resolve_project(project)
    if ctx is not None and ctx.support_telegram_username:
        return str(ctx.support_telegram_username).strip().lstrip("@")
    return (getattr(settings, "support_telegram_username", None) or "").strip().lstrip("@")


def support_telegram_public_url(
    settings: object,
    project: ProjectContext | None = None,
) -> str | None:
    """``https://t.me/{username}`` для чата поддержки (не бот)."""
    user = _support_telegram_username_clean(settings, project)
    if not user:
        return None
    return f"https://t.me/{user}"


def public_spa_base_url(
    settings: object,
    project: ProjectContext | None = None,
) -> str | None:
    """Публичный origin SPA: ``primary_domain`` проекта или ``SITE_ADDRESS`` из env."""
    ctx = _resolve_project(project)
    if ctx is not None and ctx.primary_domain:
        from_site = site_address_to_public_origin(ctx.primary_domain)
        if from_site:
            return from_site
    from_site = site_address_to_public_origin(getattr(settings, "site_address", None) or "")
    return from_site or None
