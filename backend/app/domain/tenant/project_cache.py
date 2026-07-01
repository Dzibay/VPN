"""In-memory кэш проектов с ленивой (пере)загрузкой из БД.

Проектов реально мало (единицы), они меняются редко → простой словарь без TTL,
инвалидация — по signal ``invalidate()`` при UPDATE/INSERT в /api/admin/projects.

Кэш поднимает данные для двух lookup-путей:
- Host / extra_domain → ProjectContext (публичные API, /sub/…, webhooks через Host).
- slug → ProjectContext (payment webhooks с явным slug в URL, admin selector).
- telegram_bot_api_secret → ProjectContext (bot endpoints без Host).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.project_context import ProjectContext
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.persistence.models.project import Project

log = logging.getLogger(__name__)


@dataclass
class _CacheState:
    by_id: dict[int, ProjectContext]
    by_slug: dict[str, ProjectContext]
    by_domain: dict[str, ProjectContext]  # host в нижнем регистре без порта
    by_bot_secret: dict[str, ProjectContext]


_state: _CacheState | None = None
_loaded_at: float = 0.0
_lock = asyncio.Lock()
_CACHE_TTL_SECONDS = 2.0


def _project_row_to_context(row: Project) -> ProjectContext:
    return ProjectContext(
        id=int(row.id),
        slug=str(row.slug),
        name=str(row.name),
        primary_domain=str(row.primary_domain or ""),
        extra_domains=tuple(row.extra_domains or ()),
        is_active=bool(row.is_active),
        telegram_bot_username=row.telegram_bot_username,
        telegram_bot_api_secret=row.telegram_bot_api_secret,
        support_telegram_username=row.support_telegram_username,
        support_email=row.support_email,
        tribute_api_key=row.tribute_api_key,
        yookassa_shop_id=row.yookassa_shop_id,
        yookassa_secret_key=row.yookassa_secret_key,
        yookassa_return_url=row.yookassa_return_url,
        smtp_settings=row.smtp_settings,
        referral_bonus_days_per_paid_month=row.referral_bonus_days_per_paid_month,
        referral_fixed_first_payment_bonus_rub=row.referral_fixed_first_payment_bonus_rub,
        referral_bonus_policy=row.referral_bonus_policy,
        happ_provider_id=row.happ_provider_id,
        subscription_sub_expire_banner=row.subscription_sub_expire_banner,
        subscription_sub_info_banner=row.subscription_sub_info_banner,
        brand=row.brand,
    )


def _normalize_domain(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if "://" in s:
        s = s.split("://", 1)[1]
    if "/" in s:
        s = s.split("/", 1)[0]
    if ":" in s:
        s = s.split(":", 1)[0]
    return s or None


async def _load(session: AsyncSession) -> _CacheState:
    rows = (await session.execute(select(Project))).scalars().all()
    by_id: dict[int, ProjectContext] = {}
    by_slug: dict[str, ProjectContext] = {}
    by_domain: dict[str, ProjectContext] = {}
    by_bot_secret: dict[str, ProjectContext] = {}
    for row in rows:
        ctx = _project_row_to_context(row)
        by_id[ctx.id] = ctx
        by_slug[ctx.slug.lower()] = ctx
        if not ctx.is_active:
            continue
        for raw in (ctx.primary_domain, *ctx.extra_domains):
            key = _normalize_domain(raw)
            if key:
                by_domain[key] = ctx
        if ctx.telegram_bot_api_secret:
            by_bot_secret[ctx.telegram_bot_api_secret] = ctx
    return _CacheState(
        by_id=by_id, by_slug=by_slug, by_domain=by_domain, by_bot_secret=by_bot_secret
    )


async def _ensure_loaded() -> _CacheState:
    global _loaded_at, _state
    now = time.monotonic()
    if _state is not None and now - _loaded_at <= _CACHE_TTL_SECONDS:
        return _state
    async with _lock:
        now = time.monotonic()
        if _state is not None and now - _loaded_at <= _CACHE_TTL_SECONDS:
            return _state
        async with AsyncSessionLocal() as session:
            _state = await _load(session)
            _loaded_at = time.monotonic()
            log.debug(
                "Кэш проектов загружен: %d активных доменов, %d slugs",
                len(_state.by_domain),
                len(_state.by_slug),
            )
        return _state


async def invalidate() -> None:
    """Полный сброс кэша (вызывать из admin CRUD /api/admin/projects)."""
    global _loaded_at, _state
    async with _lock:
        _state = None
        _loaded_at = 0.0


async def get_project_by_host(host: str) -> ProjectContext | None:
    normalized = _normalize_domain(host)
    if not normalized:
        return None
    state = await _ensure_loaded()
    return state.by_domain.get(normalized)


async def get_project_by_slug(slug: str) -> ProjectContext | None:
    if not slug:
        return None
    state = await _ensure_loaded()
    return state.by_slug.get(slug.strip().lower())


async def get_project_by_id(project_id: int) -> ProjectContext | None:
    state = await _ensure_loaded()
    return state.by_id.get(int(project_id))


async def get_project_by_bot_secret(secret: str) -> ProjectContext | None:
    if not secret:
        return None
    state = await _ensure_loaded()
    return state.by_bot_secret.get(secret)


async def list_active_projects() -> list[ProjectContext]:
    state = await _ensure_loaded()
    return [p for p in state.by_id.values() if p.is_active]


async def list_placeholder_frontend_domains() -> list[str]:
    """Домены проектов с brand.frontend_mode=placeholder (заглушка вместо общего SPA)."""
    domains: list[str] = []
    seen: set[str] = set()
    for project in await list_active_projects():
        brand = project.brand if isinstance(project.brand, dict) else {}
        mode = str(brand.get("frontend_mode") or "").strip().lower()
        if mode != "placeholder":
            continue
        for raw in (project.primary_domain, *project.extra_domains):
            key = _normalize_domain(raw)
            if key and key not in seen:
                seen.add(key)
                domains.append(key)
    domains.sort()
    return domains
