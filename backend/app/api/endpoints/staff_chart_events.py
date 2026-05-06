"""События на шкале графика статистики — JWT admin или manager."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.dependencies import ReadonlySessionDep, SessionDep, require_referrals_staff
from app.domain.models.staff_chart_events import (
    StaffChartEventCreate,
    StaffChartEventRead,
)
from app.domain.services.staff_chart_events_service import (
    create_staff_chart_event,
    delete_staff_chart_event,
    list_staff_chart_events,
)

router = APIRouter(
    prefix="/staff/chart-events",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "",
    response_model=list[StaffChartEventRead],
    summary="Список событий графика статистики по возрастанию event_at",
)
async def list_chart_events(session: ReadonlySessionDep) -> list[StaffChartEventRead]:
    return await list_staff_chart_events(session)


@router.post(
    "",
    response_model=StaffChartEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить событие на шкале графика",
)
async def create_chart_event(
    session: SessionDep,
    body: StaffChartEventCreate,
) -> StaffChartEventRead:
    return await create_staff_chart_event(session, body)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить событие",
)
async def delete_chart_event(
    session: SessionDep,
    event_id: int,
) -> None:
    await delete_staff_chart_event(session, event_id)
