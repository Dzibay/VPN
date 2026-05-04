"""Агрегация накопленного трафика пользователя (user_server_traffic), байты."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


def user_server_traffic_latest_subquery():
    """
    Последняя по дате строка для каждой пары (user_id, server_id).
    Суммировать все строки по пользователю нельзя — это дублирует накопление между днями.
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
        ).subquery()
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
