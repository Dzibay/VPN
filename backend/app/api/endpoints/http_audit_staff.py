"""Логи (user_http_request_traces) — admin или manager JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import ReadonlySessionDep, require_referrals_staff
from app.core.exceptions import BadRequestError
from app.domain.models.http_audit_staff import HttpRequestTraceStaffItem, HttpRequestTraceStaffPage
from app.domain.services.http_request_trace_staff_service import staff_list_http_request_traces

router = APIRouter(
    prefix="/admin/http-request-traces",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "",
    response_model=HttpRequestTraceStaffPage,
    summary="Логи (пагинация, фильтры: user_id, анонимные, status_code, subject_source)",
)
async def list_http_request_traces(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=200, description="Размер страницы")] = 50,
    offset: Annotated[int, Query(ge=0, description="Смещение")] = 0,
    user_id: Annotated[
        int | None,
        Query(gt=0, description="Только строки этого пользователя"),
    ] = None,
    only_without_user: Annotated[
        bool,
        Query(description="Только строки без user_id (анонимные / не привязанные)"),
    ] = False,
    status_code: Annotated[
        int | None,
        Query(ge=100, le=599, description="Фильтр по HTTP status code"),
    ] = None,
    subject_source: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=64,
            description="Фильтр по источнику определения user_id (subject_source)",
        ),
    ] = None,
) -> HttpRequestTraceStaffPage:
    if user_id is not None and only_without_user:
        raise BadRequestError(
            "Нельзя одновременно указывать user_id и only_without_user",
        )

    rows, total = await staff_list_http_request_traces(
        session,
        limit=limit,
        offset=offset,
        user_id=user_id,
        only_without_user=only_without_user,
        status_code=status_code,
        subject_source=subject_source,
    )
    return HttpRequestTraceStaffPage(
        items=[HttpRequestTraceStaffItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
