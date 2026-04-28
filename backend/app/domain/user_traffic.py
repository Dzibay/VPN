"""Агрегация накопленного трафика пользователя (user_server_traffic), байты."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user_server_traffic import UserServerTraffic


def user_traffic_totals(session: Session, user_id: int) -> tuple[int, int, int]:
    """Суммы up_bytes, down_bytes и их сумма по всем серверам."""
    stmt = select(
        func.coalesce(func.sum(UserServerTraffic.up_bytes), 0),
        func.coalesce(func.sum(UserServerTraffic.down_bytes), 0),
    ).where(UserServerTraffic.user_id == user_id)
    row = session.execute(stmt).one()
    up_b = int(row[0])
    down_b = int(row[1])
    return up_b, down_b, up_b + down_b
