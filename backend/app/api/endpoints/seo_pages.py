"""SEO-страницы: публичный учёт переходов и список для админки."""

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import ReadonlySessionDep, SessionDep, require_referrals_staff
from app.domain.models.seo_pages import SeoPageOut, SeoPageTrackBody
from app.domain.seo_pages.repository import increment_seo_page_views, list_seo_pages
from app.domain.tenant.admin_project_scope import admin_project_id

staff_router = APIRouter(
    prefix="/seo-pages",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)

public_router = APIRouter(prefix="/public/seo-pages", tags=["public"])


def _row_to_out(row) -> SeoPageOut:
    return SeoPageOut(
        id=int(row.id),
        path=row.path,
        title=row.title,
        views_count=int(row.views_count),
        sort_order=int(row.sort_order),
    )


@public_router.post(
    "/track",
    status_code=204,
    summary="Учёт перехода на SEO-страницу (инкремент views_count; на клиенте — один раз на браузер)",
)
async def track_seo_page_view(
    body: SeoPageTrackBody,
    session: SessionDep,
) -> Response:
    await increment_seo_page_views(session, body.path)
    return Response(status_code=204)


@staff_router.get(
    "",
    response_model=list[SeoPageOut],
    summary="Список SEO-страниц и счётчики переходов",
)
async def get_seo_pages_staff(session: ReadonlySessionDep) -> list[SeoPageOut]:
    rows = await list_seo_pages(session, project_id=admin_project_id())
    return [_row_to_out(r) for r in rows]
