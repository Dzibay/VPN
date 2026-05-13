"""Агрегация накопленного трафика пользователя (user_server_traffic), байты."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


def _user_server_traffic_ranked_by_day_subquery():
    """Строки user_server_traffic с номером по убыванию traffic_date внутри (user_id, server_id)."""
    rn = (
        func.row_number()
        .over(
            partition_by=(UserServerTraffic.user_id, UserServerTraffic.server_id),
            order_by=UserServerTraffic.traffic_date.desc(),
        )
        .label("rn")
    )
    return (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.up_bytes,
            UserServerTraffic.down_bytes,
            UserServerTraffic.traffic_date,
            rn,
        ).subquery()
    )


def user_server_traffic_latest_subquery():
    """
    Последняя по дате строка для каждой пары (user_id, server_id).
    Суммировать все строки по пользователю нельзя — это дублирует накопление между днями.
    """
    ranked = _user_server_traffic_ranked_by_day_subquery()
    return (
        select(
            ranked.c.user_id,
            ranked.c.server_id,
            ranked.c.up_bytes,
            ranked.c.down_bytes,
            ranked.c.traffic_date,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )


def user_server_traffic_latest_strictly_before_calendar_day_subquery(calendar_day: date):
    """
    На каждую пару (user_id, server_id) — последняя строка с traffic_date строго раньше calendar_day.
    """
    rn = (
        func.row_number()
        .over(
            partition_by=(UserServerTraffic.user_id, UserServerTraffic.server_id),
            order_by=UserServerTraffic.traffic_date.desc(),
        )
        .label("rn")
    )
    ranked = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.up_bytes,
            UserServerTraffic.down_bytes,
            UserServerTraffic.traffic_date,
            rn,
        )
        .where(UserServerTraffic.traffic_date < calendar_day)
        .subquery()
    )
    return (
        select(
            ranked.c.user_id,
            ranked.c.server_id,
            ranked.c.up_bytes,
            ranked.c.down_bytes,
            ranked.c.traffic_date,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )


async def user_traffic_totals(session: AsyncSession, user_id: int) -> tuple[int, int, int]:
    """Суммы up_bytes, down_bytes и их сумма по всем узлам (последний снимок на узел)."""
    latest = user_server_traffic_latest_subquery()
    stmt = select(
        func.coalesce(func.sum(latest.c.up_bytes), 0),
        func.coalesce(func.sum(latest.c.down_bytes), 0),
    ).where(latest.c.user_id == user_id)
    row = (await session.execute(stmt)).one()
    up_b = int(row[0])
    down_b = int(row[1])
    return up_b, down_b, up_b + down_b


async def _user_traffic_total_by_user_at_cutoff(
    session: AsyncSession,
    calendar_day_utc: date,
    *,
    inclusive: bool,
) -> dict[int, int]:
    """Сумма по пользователю: на каждом узле последняя строка с датой до границы (строго или включительно)."""
    cutoff = (
        UserServerTraffic.traffic_date <= calendar_day_utc
        if inclusive
        else UserServerTraffic.traffic_date < calendar_day_utc
    )
    rn = (
        func.row_number()
        .over(
            partition_by=(UserServerTraffic.user_id, UserServerTraffic.server_id),
            order_by=UserServerTraffic.traffic_date.desc(),
        )
        .label("rn")
    )
    ranked = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.up_bytes,
            UserServerTraffic.down_bytes,
            rn,
        )
        .where(cutoff)
        .subquery()
    )
    latest = (
        select(
            ranked.c.user_id,
            ranked.c.server_id,
            ranked.c.up_bytes,
            ranked.c.down_bytes,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )
    stmt = select(
        latest.c.user_id,
        func.coalesce(func.sum(latest.c.up_bytes + latest.c.down_bytes), 0).label("total"),
    ).group_by(latest.c.user_id)
    rows = (await session.execute(stmt)).all()
    out: dict[int, int] = {}
    for uid_raw, tot_raw in rows:
        uid = int(uid_raw)
        tot = int(tot_raw or 0)
        if tot < 0:
            tot = 0
        out[uid] = tot
    return out


async def user_traffic_total_by_user_as_of(
    session: AsyncSession,
    as_of_calendar_day_utc: date,
) -> dict[int, int]:
    """Суммарный накопленный трафик по каждому user_id на конец календарного дня UTC ``as_of``.

    На каждом узле берётся последняя строка с ``traffic_date <= as_of`` (как в дневной метрике
    «активные пользователи»). Пользователи без строк в ``user_server_traffic`` не попадают в словарь.
    """
    return await _user_traffic_total_by_user_at_cutoff(
        session,
        as_of_calendar_day_utc,
        inclusive=True,
    )


async def user_traffic_total_by_user_strictly_before_calendar_day(
    session: AsyncSession,
    calendar_day_utc: date,
) -> dict[int, int]:
    """Сумма по user_id: на каждом узле последняя строка с ``traffic_date`` строго до ``calendar_day_utc``."""
    return await _user_traffic_total_by_user_at_cutoff(
        session,
        calendar_day_utc,
        inclusive=False,
    )
