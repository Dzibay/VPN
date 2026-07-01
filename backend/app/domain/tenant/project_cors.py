"""CORS allow-list, собранный из глобальных настроек + доменов активных проектов.

Читаем `projects.primary_domain` + `extra_domains` синхронно из БД на старте приложения
(до первого запроса) и сохраняем как ``list[str]`` для передачи в ``CORSMiddleware``.
Изменение доменов проектов требует перезапуска процесса — статичный список пере-инстанциировать
на лету нельзя (Starlette CORSMiddleware хранит его в атрибуте).

Для динамического рантайм-режима admin API может держать regex, покрывающий все
известные домены (см. Settings.cors_origin_regex).
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text

from app.config import settings

log = logging.getLogger(__name__)


def _sync_load_project_origins() -> list[str]:
    """Синхронно читает домены активных проектов до старта event loop."""
    origins: list[str] = []
    try:
        engine = create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT primary_domain, extra_domains FROM projects WHERE is_active = TRUE"
                )
            ).all()
    except Exception:
        log.warning(
            "Не удалось прочитать projects.primary_domain для CORS (БД ещё не готова?), "
            "используем только глобальные cors_origins",
        )
        return origins

    for primary, extras in rows:
        for raw in (primary, *(list(extras or []))):
            if not raw:
                continue
            domain = str(raw).strip()
            if not domain:
                continue
            for scheme in ("https", "http"):
                origins.append(f"{scheme}://{domain}")
    return origins


def build_cors_allow_origins() -> list[str]:
    """Возвращает финальный список origin для CORSMiddleware."""
    from app.domain.subscription.public_base import site_address_to_public_origin

    seen: set[str] = set()
    out: list[str] = []
    for origin in settings.cors_origins:
        if origin not in seen:
            seen.add(origin)
            out.append(origin)
    # Legacy site_address / site_extra_addresses — оставляем как fallback для
    # инсталляций, где projects таблица ещё не наполнена.
    for raw in [settings.site_address, *settings.site_extra_addresses]:
        origin = site_address_to_public_origin(raw)
        if origin and origin not in seen:
            seen.add(origin)
            out.append(origin)
    # Отдельный домен админки (staff-панель): чтобы браузер мог слать запросы к
    # /api с Authorization + X-Admin-Project, если API живёт на другом Host.
    admin_origin = site_address_to_public_origin(settings.admin_site_address)
    if admin_origin and admin_origin not in seen:
        seen.add(admin_origin)
        out.append(admin_origin)
    for origin in _sync_load_project_origins():
        if origin not in seen:
            seen.add(origin)
            out.append(origin)
    return out
