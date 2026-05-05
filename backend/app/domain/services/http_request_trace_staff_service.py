"""Список строк user_http_request_traces для админки."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.user_http_request_trace import UserHttpRequestTrace


async def staff_list_http_request_traces(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    user_id: int | None,
    only_without_user: bool,
    status_code: int | None,
    subject_source: str | None,
) -> tuple[list[UserHttpRequestTrace], int]:
    filters: list = []
    if user_id is not None:
        filters.append(UserHttpRequestTrace.user_id == user_id)
    elif only_without_user:
        filters.append(UserHttpRequestTrace.user_id.is_(None))
    if status_code is not None:
        filters.append(UserHttpRequestTrace.status_code == status_code)
    src = (subject_source or "").strip()
    if src:
        filters.append(UserHttpRequestTrace.subject_source == src)

    cnt_q = select(func.count(UserHttpRequestTrace.id))
    list_q = select(UserHttpRequestTrace).order_by(UserHttpRequestTrace.created_at.desc())
    if filters:
        cnt_q = cnt_q.where(*filters)
        list_q = list_q.where(*filters)

    total = int((await session.execute(cnt_q)).scalar_one() or 0)
    list_q = list_q.limit(limit).offset(offset)
    rows = list((await session.scalars(list_q)).all())
    return rows, total


async def staff_delete_http_request_traces_by_ids(
    session: AsyncSession,
    *,
    ids: list[int],
) -> int:
    uniq_ids = sorted({int(v) for v in ids if int(v) > 0})
    if not uniq_ids:
        return 0
    res = await session.execute(
        delete(UserHttpRequestTrace).where(UserHttpRequestTrace.id.in_(uniq_ids)),
    )
    await session.commit()
    return int(res.rowcount or 0)
