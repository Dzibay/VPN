from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import ReadonlySessionDep, require_referrals_staff
from app.core.exceptions import BadRequestError
from app.core.time import moscow_today
from app.domain.models.admin_summary import AdminSummaryResponse
from app.domain.services.admin_summary_service import get_admin_summary

admin_summary_router = APIRouter(
    prefix="/admin/summary",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


def _default_range() -> tuple[date, date]:
    today = moscow_today()
    return today, today


@admin_summary_router.get(
    "",
    response_model=AdminSummaryResponse,
    summary="Сводка админки за период",
    description="KPI: пользователи, подписки, доход и конверсия. "
    "Календарь Europe/Moscow. По умолчанию — сегодня.",
)
async def admin_summary(
    session: ReadonlySessionDep,
    date_from: Annotated[date | None, Query(alias="from", description="YYYY-MM-DD")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="YYYY-MM-DD")] = None,
) -> AdminSummaryResponse:
    d_from, d_to = _default_range()
    if date_from is not None:
        d_from = date_from
    if date_to is not None:
        d_to = date_to
    if d_from > d_to:
        raise BadRequestError("Начало диапазона позже его конца")
    return await get_admin_summary(session, date_from=d_from, date_to=d_to)
