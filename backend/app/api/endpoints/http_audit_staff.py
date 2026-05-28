"""Логи (user_http_request_traces) — admin или manager JWT."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    require_admin,
    require_referrals_staff,
)
from app.core.exceptions import BadRequestError
from app.core.time import ensure_utc
from app.domain.models.http_audit_staff import (
    HttpRequestTraceBulkDeleteBody,
    HttpRequestTraceBulkDeleteResponse,
    HttpRequestTraceStaffItem,
    HttpRequestTraceStaffPage,
)
from app.domain.services.http_request_trace_staff_service import (
    staff_delete_http_request_traces_by_ids,
    staff_list_http_request_traces,
)

router = APIRouter(
    prefix="/admin/http-request-traces",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "",
    response_model=HttpRequestTraceStaffPage,
    summary=(
        "Логи (пагинация, фильтры: user_id, анонимные, status_code[], "
        "subject_source[], path_contains, created_from, created_to)"
    ),
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
        list[int] | None,
        Query(description="Фильтр по HTTP status code (можно несколько значений)"),
    ] = None,
    subject_source: Annotated[
        list[str] | None,
        Query(description="Фильтр по источнику определения user_id (можно несколько)"),
    ] = None,
    path_contains: Annotated[
        str | None,
        Query(
            description="Подстрока пути запроса (path содержит это значение, без шаблонов)",
            max_length=512,
        ),
    ] = None,
    created_from: Annotated[
        datetime | None,
        Query(description="Нижняя граница created_at (включительно), ISO 8601"),
    ] = None,
    created_to: Annotated[
        datetime | None,
        Query(description="Верхняя граница created_at (включительно), ISO 8601"),
    ] = None,
) -> HttpRequestTraceStaffPage:
    if user_id is not None and only_without_user:
        raise BadRequestError(
            "Нельзя одновременно указывать user_id и only_without_user",
        )

    status_codes = sorted({v for v in (status_code or []) if 100 <= int(v) <= 599})
    if (status_code or []) and not status_codes:
        raise BadRequestError("Некорректный status_code")
    subject_sources = []
    for raw in subject_source or []:
        s = str(raw).strip()
        if not s:
            continue
        if len(s) > 64:
            raise BadRequestError("subject_source должен быть не длиннее 64 символов")
        subject_sources.append(s)
    subject_sources = sorted(set(subject_sources))

    path_sub = str(path_contains).strip() if path_contains is not None else ""
    path_filter = path_sub or None

    created_from_utc = (
        ensure_utc(created_from) if created_from is not None else None
    )
    created_to_utc = ensure_utc(created_to) if created_to is not None else None
    if (
        created_from_utc is not None
        and created_to_utc is not None
        and created_from_utc > created_to_utc
    ):
        raise BadRequestError("created_from не может быть позже created_to")

    rows, total = await staff_list_http_request_traces(
        session,
        limit=limit,
        offset=offset,
        user_id=user_id,
        only_without_user=only_without_user,
        status_codes=status_codes or None,
        subject_sources=subject_sources or None,
        path_contains=path_filter,
        created_from=created_from_utc,
        created_to=created_to_utc,
    )
    return HttpRequestTraceStaffPage(
        items=[HttpRequestTraceStaffItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "",
    response_model=HttpRequestTraceBulkDeleteResponse,
    summary="Удаление выбранных логов по списку id",
)
async def delete_http_request_traces(
    body: HttpRequestTraceBulkDeleteBody,
    session: SessionDep,
    _: Annotated[None, Depends(require_admin)],
) -> HttpRequestTraceBulkDeleteResponse:
    if not body.ids:
        raise BadRequestError("Нужно передать хотя бы один id")
    deleted = await staff_delete_http_request_traces_by_ids(
        session,
        ids=body.ids,
    )
    return HttpRequestTraceBulkDeleteResponse(deleted_count=deleted)
