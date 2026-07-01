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


async def ensure_seo_pages_catalog(session: AsyncSession, *, project_id: int = 1) -> None:
    """Идемпотентно синхронизирует каталог SEO-страниц с кодом (для дефолтного проекта id=1)."""
    for path, title, sort_order in SEO_PAGES_CATALOG:
        stmt = (
            insert(SeoPage)
            .values(project_id=project_id, path=path, title=title, sort_order=sort_order)
            .on_conflict_do_nothing(index_elements=[SeoPage.project_id, SeoPage.path])
        )
        await session.execute(stmt)

    await session.execute(
        delete(SeoPage).where(
            SeoPage.project_id == project_id,
            SeoPage.path.not_in(SEO_PAGE_PATHS),
        ),
    )


async def increment_seo_page_views_for_project(
    session: AsyncSession, *, project_id: int, path: str
) -> bool:
    normalized = normalize_seo_path(path)
    res = await session.execute(
        update(SeoPage)
        .where(SeoPage.project_id == project_id, SeoPage.path == normalized)
        .values(views_count=SeoPage.views_count + 1),
    )
    return res.rowcount > 0


async def increment_seo_page_views(session: AsyncSession, path: str) -> bool:
    """Атомарный +1 к счётчику; ``True`` — если страница найдена.

    Multi-tenant: определяет проект из текущего context (см. ProjectContextMiddleware),
    fallback на project_id=1 (legacy).
    """
    from app.domain.tenant.project_context import get_current_project

    project = get_current_project()
    project_id = project.id if project is not None else 1
    return await increment_seo_page_views_for_project(
        session, project_id=project_id, path=path
    )


async def list_seo_pages(session: AsyncSession, *, project_id: int | None = None) -> list[SeoPage]:
    stmt = select(SeoPage).order_by(SeoPage.sort_order.asc(), SeoPage.id.asc())
    if project_id is not None:
        stmt = stmt.where(SeoPage.project_id == project_id)
    return list(await session.scalars(stmt))
