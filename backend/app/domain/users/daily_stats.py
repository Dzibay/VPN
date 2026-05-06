"""Системные дневные метрики: регистрации, активные пользователи, первые подписочные устройства.

Все агрегаты группируются по календарной дате UTC (``traffic_date`` хранится как DATE,
``registered_at`` — как TIMESTAMP, явный ``timezone('UTC', …)`` снимает зависимость от настроек
сессии). «Активный пользователь за день» — у которого хотя бы по одному из узлов суммарный
трафик увеличился по сравнению с концом предыдущего дня.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import as_calendar_date
from app.domain.models.users import UserStatsByDateRow, UsersDailyStatsResponse
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


async def _traffic_active_count_by_date(
    session: AsyncSession,
    *,
    user_ids_filter: set[int] | None = None,
) -> dict[date, int]:
    """День → число «активных» пользователей.

    Активный = в этот день суммарный трафик пользователя по всем узлам стал больше, чем
    был вчера (на стыке между концом вчерашнего дня и концом сегодняшнего).
    """
    stmt = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
        )
        .order_by(
            UserServerTraffic.user_id.asc(),
            UserServerTraffic.server_id.asc(),
            UserServerTraffic.traffic_date.asc(),
        )
    )
    raw = (await session.execute(stmt)).all()
    by_user: dict[int, dict[int, list[tuple[date, int]]]] = defaultdict(
        lambda: defaultdict(list),
    )
    all_dates: set[date] = set()
    for uid_raw, sid_raw, td_raw, tot_raw in raw:
        cal = as_calendar_date(td_raw)
        if cal is None:
            continue
        tot = int(tot_raw or 0)
        if tot < 0:
            tot = 0
        uid = int(uid_raw)
        if user_ids_filter is not None and uid not in user_ids_filter:
            continue
        sid = int(sid_raw)
        by_user[uid][sid].append((cal, tot))
        all_dates.add(cal)
    if not all_dates:
        return {}
    min_d = min(all_dates)
    max_d = max(all_dates)
    day_list: list[date] = []
    d = min_d
    while d <= max_d:
        day_list.append(d)
        d += timedelta(days=1)

    user_states: dict[int, dict[str, object]] = {}
    for uid, servers_map in by_user.items():
        for sid in servers_map:
            servers_map[sid].sort(key=lambda x: x[0])
        user_states[uid] = {
            "idx": {sid: 0 for sid in servers_map},
            "cur": {sid: 0 for sid in servers_map},
            "prev_total": 0,
        }

    result: dict[date, int] = {}
    for cal_day in day_list:
        active = 0
        for uid, st in user_states.items():
            servers_map = by_user[uid]
            idx_map = st["idx"]
            cur_map = st["cur"]
            assert isinstance(idx_map, dict)
            assert isinstance(cur_map, dict)
            for sid, series in servers_map.items():
                i = int(idx_map[sid])
                while i < len(series) and series[i][0] <= cal_day:
                    cur_map[sid] = series[i][1]
                    i += 1
                idx_map[sid] = i
            total = int(sum(int(cur_map[sid]) for sid in servers_map))
            prev_total = int(st["prev_total"])
            if total > prev_total:
                active += 1
            st["prev_total"] = total
        result[cal_day] = active
    return result


async def stats_by_date_merged(session: AsyncSession) -> list[UserStatsByDateRow]:
    """Сводка по датам через PostgreSQL ``rpc_users_daily_stats()`` (см. ``database/rpc/users_daily_stats.sql``).

    Строка без даты регистрации (``stats_date IS NULL``) — в конце набора, если есть такие пользователи.
    """
    stmt = text(
        """
        SELECT stats_date, users_count, users_with_traffic_count,
               active_users_count, subscription_devices_users_count
        FROM rpc_users_daily_stats()
        """,
    )
    rows = (await session.execute(stmt)).all()
    return [
        UserStatsByDateRow(
            stats_date=row[0],
            users_count=int(row[1] or 0),
            users_with_traffic_count=int(row[2] or 0),
            active_users_count=int(row[3] or 0),
            subscription_devices_users_count=int(row[4] or 0),
        )
        for row in rows
    ]


async def users_daily_stats(session: AsyncSession) -> UsersDailyStatsResponse:
    """Готовый response-объект с ежедневной сводкой (для эндпоинта ``/users/daily-stats``)."""
    return UsersDailyStatsResponse(stats_by_date=await stats_by_date_merged(session))


async def count_users_with_subscription_device(
    session: AsyncSession,
    referral_link_id: int | None,
) -> int:
    """Число пользователей с хотя бы одной записью в ``subscription_devices``.

    При ``referral_link_id`` фильтрует по реферальной ссылке (для статистики кампаний).
    """
    stmt = select(func.count(func.distinct(SubscriptionDevice.user_id))).select_from(
        SubscriptionDevice,
    ).join(User, User.id == SubscriptionDevice.user_id)
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return int(await session.scalar(stmt) or 0)


async def active_users_count_for_utc_date(
    session: AsyncSession,
    cal_day: date,
    referral_link_id: int | None,
) -> int:
    """Сколько «активных» пользователей за конкретный календарный день UTC.

    Та же метрика, что в ``users_daily_stats``, но за один день и с возможностью фильтрации
    по ``referral_link_id``.
    """
    filt: set[int] | None = None
    if referral_link_id is not None:
        ids_raw = (
            await session.scalars(
                select(User.id).where(User.referral_link_id == referral_link_id),
            )
        ).all()
        filt = {int(i) for i in ids_raw}
    m = await _traffic_active_count_by_date(session, user_ids_filter=filt)
    return int(m.get(cal_day, 0) or 0)
