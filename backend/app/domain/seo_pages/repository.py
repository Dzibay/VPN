from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.seo_pages.catalog import SEO_PAGES_CATALOG, SEO_PAGE_PATHS
from app.infrastructure.persistence.models.seo_page import SeoPage


def normalize_seo_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    if len(raw) > 1 and raw.endswith("/"):
        raw = raw.rstrip("/")
    return raw or "/"


async def ensure_seo_pages_catalog(session: AsyncSession) -> None:
    """Идемпотентно синхронизирует каталог SEO-страниц с кодом."""
    for path, title, sort_order in SEO_PAGES_CATALOG:
        stmt = (
            insert(SeoPage)
            .values(path=path, title=title, sort_order=sort_order)
            .on_conflict_do_nothing(index_elements=[SeoPage.path])
        )
        await session.execute(stmt)

    await session.execute(
        delete(SeoPage).where(SeoPage.path.not_in(SEO_PAGE_PATHS)),
    )


async def increment_seo_page_views(session: AsyncSession, path: str) -> bool:
    """Атомарный +1 к счётчику; ``True`` — если страница найдена."""
    normalized = normalize_seo_path(path)
    res = await session.execute(
        update(SeoPage)
        .where(SeoPage.path == normalized)
        .values(views_count=SeoPage.views_count + 1),
    )
    return res.rowcount > 0


async def list_seo_pages(session: AsyncSession) -> list[SeoPage]:
    return list(
        await session.scalars(
            select(SeoPage).order_by(SeoPage.sort_order.asc(), SeoPage.id.asc()),
        ),
    )
