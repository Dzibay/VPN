"""Per-user breakdown трафика для админских экранов: по узлам и накопительный по дням."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.time import as_calendar_date
from app.domain.traffic_daily import cumulative_traffic_by_calendar_days
from app.domain.models.server_traffic import (
    UserTrafficByDayRow,
    UserTrafficByServersBundle,
    UserTrafficPerServerRow,
)
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


async def user_traffic_cumulative_by_day_rows(
    session: AsyncSession,
    user_id: int,
) -> list[UserTrafficByDayRow]:
    """Накопительный по календарному дню (UTC) трафик пользователя по всем узлам.

    На каждый общий маркер дня из истории строки ``user_server_traffic`` суммируем
    последнее зафиксированное значение по каждому узлу — получаем правильный «прирост на дату»,
    даже если узлы фиксировались в разные дни.
    """
    stmt = (
        select(
            UserServerTraffic.server_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
        )
        .where(UserServerTraffic.user_id == user_id)
        .order_by(UserServerTraffic.server_id.asc(), UserServerTraffic.traffic_date.asc())
    )
    rows_raw = (await session.execute(stmt)).all()
    by_server: dict[int, list[tuple[date, int]]] = {}
    for sid_raw, td_raw, total_raw in rows_raw:
        cal = as_calendar_date(td_raw)
        if cal is None:
            continue
        sid = int(sid_raw)
        tot = int(total_raw or 0)
        if tot < 0:
            tot = 0
        by_server.setdefault(sid, []).append((cal, tot))
    pairs = cumulative_traffic_by_calendar_days(by_server)
    return [
        UserTrafficByDayRow(traffic_date=d, cumulative_bytes=cumulative)
        for d, cumulative in pairs
    ]


async def user_traffic_by_servers_bundle(
    session: AsyncSession,
    user_id: int,
) -> UserTrafficByServersBundle:
    """Распределение трафика пользователя по узлам с метаданными узла.

    Возвращает строки по всем серверам (не только тем, где есть статистика), чтобы UI всегда
    показывал полный список узлов из админ-кабинета.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    latest = user_server_traffic_latest_subquery().alias("ut_latest")
    stmt = (
        select(Server, latest.c.up_bytes, latest.c.down_bytes)
        .select_from(Server)
        .outerjoin(
            latest,
            and_(
                latest.c.server_id == Server.id,
                latest.c.user_id == user_id,
            ),
        )
        .order_by(Server.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    out: list[UserTrafficPerServerRow] = []
    total_up = 0
    total_down = 0
    for srv, up_raw, down_raw in rows:
        up = int(up_raw or 0)
        down = int(down_raw or 0)
        total_up += up
        total_down += down
        out.append(
            UserTrafficPerServerRow(
                server_id=srv.id,
                name=srv.name,
                host=srv.host,
                port=srv.port,
                country=srv.country or "",
                is_active=srv.is_active,
                provision_ready=srv.provision_ready,
                up_bytes=up,
                down_bytes=down,
                total_bytes=up + down,
            ),
        )
    return UserTrafficByServersBundle(
        user_id=user.id,
        telegram_id=user.telegram_id,
        subscription_until=user.subscription_until,
        servers=out,
        total_up_bytes=total_up,
        total_down_bytes=total_down,
    )
