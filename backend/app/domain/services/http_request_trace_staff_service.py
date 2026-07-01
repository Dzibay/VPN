"""Список строк user_http_request_traces для админки."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.list_sort import SortDir, order_clause
from app.domain.tenant.admin_project_scope import project_scope_clause
from app.infrastructure.persistence.models.user_http_request_trace import UserHttpRequestTrace

_HTTP_TRACE_SORT_KEYS = frozenset({
    "created_at",
    "user_id",
    "subject_source",
    "http_method",
    "path",
    "status_code",
    "duration_ms",
    "client_ip",
})


def _http_trace_list_order_by(sort_by: str | None, sort_dir: SortDir):
    if sort_by is None or sort_by not in _HTTP_TRACE_SORT_KEYS:
        return (UserHttpRequestTrace.created_at.desc(),)
    columns = {
        "created_at": UserHttpRequestTrace.created_at,
        "user_id": UserHttpRequestTrace.user_id,
        "subject_source": UserHttpRequestTrace.subject_source,
        "http_method": UserHttpRequestTrace.http_method,
        "path": UserHttpRequestTrace.path,
        "status_code": UserHttpRequestTrace.status_code,
        "duration_ms": UserHttpRequestTrace.duration_ms,
        "client_ip": UserHttpRequestTrace.client_ip,
    }
    primary = columns[sort_by]
    clauses = [order_clause(primary, sort_dir)]
    if sort_by != "created_at":
        clauses.append(UserHttpRequestTrace.created_at.desc())
    return tuple(clauses)


async def staff_list_http_request_traces(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    user_id: int | None,
    only_without_user: bool,
    status_codes: list[int] | None,
    subject_sources: list[str] | None,
    path_contains: str | None,
    client_ip_contains: str | None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort_by: str | None = None,
    sort_dir: SortDir = "asc",
) -> tuple[list[UserHttpRequestTrace], int]:
    filters: list = []
    if user_id is not None:
        filters.append(UserHttpRequestTrace.user_id == user_id)
    elif only_without_user:
        filters.append(UserHttpRequestTrace.user_id.is_(None))
    if status_codes:
        filters.append(UserHttpRequestTrace.status_code.in_(status_codes))
    if subject_sources:
        filters.append(UserHttpRequestTrace.subject_source.in_(subject_sources))
    if path_contains:
        filters.append(func.strpos(UserHttpRequestTrace.path, path_contains) > 0)
    if client_ip_contains:
        filters.append(func.strpos(UserHttpRequestTrace.client_ip, client_ip_contains) > 0)
    if created_from is not None:
        filters.append(UserHttpRequestTrace.created_at >= created_from)
    if created_to is not None:
        filters.append(UserHttpRequestTrace.created_at <= created_to)

    scope = project_scope_clause(UserHttpRequestTrace)
    if scope is not None:
        filters.append(scope)

    cnt_q = select(func.count(UserHttpRequestTrace.id))
    list_q = select(UserHttpRequestTrace).order_by(
        *_http_trace_list_order_by(sort_by, sort_dir),
    )
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
