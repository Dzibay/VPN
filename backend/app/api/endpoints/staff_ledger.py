"""Админка: списки payments и tasks (JWT admin или manager)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import ReadonlySessionDep, require_referrals_staff
from app.domain.models.staff_ledger import (
    StaffPaymentsListResponse,
    StaffTasksListResponse,
)
from app.domain.services.staff_ledger_service import list_staff_payments, list_staff_tasks

payments_staff_router = APIRouter(
    prefix="/admin/payments",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)

tasks_staff_router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@payments_staff_router.get(
    "",
    response_model=StaffPaymentsListResponse,
    summary="Список платежей (payments)",
)
async def staff_list_payments(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000, description="Максимум строк в ответе")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение от новых к старым")] = 0,
) -> StaffPaymentsListResponse:
    items, total = await list_staff_payments(session, limit=limit, offset=offset)
    return StaffPaymentsListResponse(items=items, total=total, limit=limit, offset=offset)


@tasks_staff_router.get(
    "",
    response_model=StaffTasksListResponse,
    summary="Список задач (tasks)",
)
async def staff_list_tasks(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000, description="Максимум строк в ответе")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение от новых к старым")] = 0,
) -> StaffTasksListResponse:
    items, total = await list_staff_tasks(session, limit=limit, offset=offset)
    return StaffTasksListResponse(items=items, total=total, limit=limit, offset=offset)
