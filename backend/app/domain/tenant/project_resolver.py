"""Резолвинг проекта по HTTP-запросу.

Порядок:
1. Заголовок ``X-Admin-Project`` (slug или '__all__') — приоритетно для админ-панели;
   позволяет staff-запросам с admin.<domain> явно указать проект вне зависимости от Host.
2. Явный slug в URL для payment webhooks: ``/api/payments/{provider}/webhook/{slug}``.
3. Host / X-Forwarded-Host (алиас домена → primary_domain).
4. Заголовок ``X-Telegram-Bot-Secret`` — секрет содержится в ``projects.telegram_bot_api_secret``.
5. Fallback на дефолтный проект (project_id=1) — только для endpoints без tenant-scope
   (например, health, prometheus SD). Не должен применяться для tenant-endpoints — там 404.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.tenant.project_cache import (
    get_project_by_bot_secret,
    get_project_by_host,
    get_project_by_slug,
)
from app.domain.tenant.project_context import ProjectContext

# /api/payments/tribute/webhook/{slug} или /api/payments/yookassa/webhook/{slug}
_WEBHOOK_URL_RE = re.compile(
    r"^/api/payments/(?:tribute|yookassa)/webhook/(?P<slug>[a-zA-Z0-9_-]+)/?$"
)


def _extract_header(scope_or_request: Any, name: str) -> str | None:
    """Работает и с ASGI scope (headers = list of (bytes, bytes)), и с ``fastapi.Request``."""
    # fastapi.Request
    if hasattr(scope_or_request, "headers"):
        val = scope_or_request.headers.get(name)
        if val is None:
            val = scope_or_request.headers.get(name.lower())
        return val
    scope = scope_or_request
    name_lc = name.lower().encode("latin-1")
    for k, v in scope.get("headers") or ():
        if k == name_lc:
            try:
                return v.decode("latin-1")
            except Exception:
                return None
    return None


def _extract_path(scope_or_request: Any) -> str:
    if hasattr(scope_or_request, "url"):
        try:
            return scope_or_request.url.path
        except Exception:
            pass
    return str(scope_or_request.get("path") or "")


def _extract_host(scope_or_request: Any) -> str | None:
    # Fastapi Request → request.url.hostname (без порта) как основной вариант.
    if hasattr(scope_or_request, "url"):
        try:
            hostname = scope_or_request.url.hostname
            if hostname:
                return hostname
        except Exception:
            pass
    xfh = _extract_header(scope_or_request, "x-forwarded-host")
    if xfh:
        # Может быть comma-separated список — берём первый.
        return xfh.split(",", 1)[0].strip()
    return _extract_header(scope_or_request, "host")


async def resolve_project(scope_or_request: Any) -> ProjectContext | None:
    """Возвращает проект или None (никаких исключений — решение о 404 принимают dependencies)."""
    path = _extract_path(scope_or_request)

    # 1. X-Admin-Project: явный выбор проекта из админки. Значение '__all__' /
    #    'all' → None (агрегатный режим, разрешён super_admin dependency-фильтром).
    admin_slug = _extract_header(scope_or_request, "x-admin-project")
    if admin_slug:
        slug_norm = admin_slug.strip().lower()
        if slug_norm in ("__all__", "all", ""):
            return None
        by_admin = await get_project_by_slug(slug_norm)
        if by_admin is not None:
            return by_admin
        # Явно указан, но не найден — не откатываемся на Host (это была бы утечка).
        return None

    # 2. Payment webhook: явный slug в URL.
    m = _WEBHOOK_URL_RE.match(path)
    if m:
        slug = m.group("slug")
        by_slug = await get_project_by_slug(slug)
        if by_slug is not None:
            return by_slug

    # 3. Bot секрет в заголовке (без Host, если бот стучится напрямую на IP).
    bot_secret = _extract_header(scope_or_request, "x-telegram-bot-secret")
    if bot_secret:
        by_secret = await get_project_by_bot_secret(bot_secret.strip())
        if by_secret is not None:
            return by_secret

    # 4. Host / X-Forwarded-Host.
    host = _extract_host(scope_or_request)
    if host:
        by_host = await get_project_by_host(host)
        if by_host is not None:
            return by_host

    return None
