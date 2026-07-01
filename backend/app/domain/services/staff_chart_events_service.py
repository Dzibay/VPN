from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.domain.models.staff_chart_events import StaffChartEventCreate, StaffChartEventRead
from app.domain.tenant.admin_project_scope import apply_project_scope
from app.infrastructure.persistence.models.staff_chart_event import StaffChartEvent


async def list_staff_chart_events(session: AsyncSession) -> list[StaffChartEventRead]:
    stmt = apply_project_scope(
        select(StaffChartEvent).order_by(StaffChartEvent.event_at.asc()),
        StaffChartEvent,
    )
    rows = (await session.scalars(stmt)).all()
    return [StaffChartEventRead.model_validate(r) for r in rows]


async def create_staff_chart_event(
    session: AsyncSession,
    body: StaffChartEventCreate,
) -> StaffChartEventRead:
    row = StaffChartEvent(
        event_at=body.event_at,
        title=body.title,
        color=body.color,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return StaffChartEventRead.model_validate(row)


async def delete_staff_chart_event(session: AsyncSession, event_id: int) -> None:
    stmt = delete(StaffChartEvent).where(StaffChartEvent.id == event_id)
    res = await session.execute(stmt)
    if res.rowcount == 0:
        raise NotFoundError("Событие не найдено")
