"""Дневные ряды по ``user_server_traffic`` (календарный ``traffic_date`` = UTC на момент сбора)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import as_calendar_date, iter_calendar_days
from app.domain.users.stats_qualification import user_counts_in_admin_stats
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic

UserTrafficSeries = dict[int, dict[int, list[tuple[date, int]]]]


async def fetch_user_traffic_series(
    session: AsyncSession,
    *,
    user_ids_filter: set[int] | None = None,
    eligible_users_only: bool = False,
) -> UserTrafficSeries:
    """``user_id`` → ``server_id`` → отсортированные ``(traffic_date, bytes)`` (max на день/узел)."""

    stmt = select(
        UserServerTraffic.user_id,
        UserServerTraffic.server_id,
        UserServerTraffic.traffic_date,
        UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
    ).select_from(UserServerTraffic)
    if eligible_users_only:
        stmt = stmt.join(User, User.id == UserServerTraffic.user_id).where(
            user_counts_in_admin_stats(User),
            User.registered_at.is_not(None),
            User.subscription_until.is_not(None),
        )
    if user_ids_filter is not None:
        if not user_ids_filter:
            return {}
        stmt = stmt.where(UserServerTraffic.user_id.in_(user_ids_filter))
    stmt = stmt.order_by(
        UserServerTraffic.user_id.asc(),
        UserServerTraffic.server_id.asc(),
        UserServerTraffic.traffic_date.asc(),
    )
    raw = (await session.execute(stmt)).all()
    by_user: UserTrafficSeries = defaultdict(lambda: defaultdict(list))
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

    for uid in by_user:
        for sid in by_user[uid]:
            series = by_user[uid][sid]
            series.sort(key=lambda x: x[0])
            by_day: dict[date, int] = {}
            for cal, bt in series:
                b = int(bt or 0)
                if b < 0:
                    b = 0
                prev = by_day.get(cal, 0)
                if b > prev:
                    by_day[cal] = b
            by_user[uid][sid] = sorted(by_day.items(), key=lambda x: x[0])
    return by_user


def traffic_day_span(series_by_user: UserTrafficSeries) -> list[date]:
    """Плотный список календарных дней UTC от min до max ``traffic_date`` в выборке."""

    all_dates: set[date] = set()
    for servers in series_by_user.values():
        for pts in servers.values():
            for cal, _ in pts:
                all_dates.add(cal)
    if not all_dates:
        return []
    return iter_calendar_days(min(all_dates), max(all_dates))


def active_users_count_by_traffic_day(
    series_by_user: UserTrafficSeries,
    day_list: list[date] | None = None,
) -> dict[date, int]:
    """Число пользователей с ростом суммарного трафика в каждый ``traffic_date``."""

    if day_list is None:
        day_list = traffic_day_span(series_by_user)
    if not day_list:
        return {}

    user_states: dict[int, dict[str, object]] = {}
    for uid, servers_map in series_by_user.items():
        user_states[uid] = {
            "idx": {sid: 0 for sid in servers_map},
            "cur": {sid: 0 for sid in servers_map},
            "prev_total": 0,
        }

    result: dict[date, int] = {}
    for cal_day in day_list:
        active = 0
        for uid, st in user_states.items():
            servers_map = series_by_user[uid]
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


def user_bytes_total_at(
    servers_map: dict[int, list[tuple[date, int]]],
    end: date,
) -> int:
    """Суммарные байты пользователя на конец календарного дня ``end`` (последний снимок ≤ end на узел)."""

    import bisect

    total = 0
    for series in servers_map.values():
        if not series:
            continue
        dates = [t[0] for t in series]
        i = bisect.bisect_right(dates, end) - 1
        if i >= 0:
            total += int(series[i][1] or 0)
    return total


def cumulative_traffic_by_calendar_days(
    by_server: dict[int, list[tuple[date, int]]],
) -> list[tuple[date, int]]:
    """Накопительная сумма по маркерам ``traffic_date``: forward-fill на узел, затем сумма."""

    day_markers: set[date] = set()
    for series in by_server.values():
        for cal, _ in series:
            day_markers.add(cal)
    if not day_markers:
        return []
    servers = sorted(by_server.keys())
    indices = {sid: 0 for sid in servers}
    current = {sid: 0 for sid in servers}
    out: list[tuple[date, int]] = []
    for d in sorted(day_markers):
        for sid in servers:
            series = by_server[sid]
            i = indices[sid]
            while i < len(series) and series[i][0] <= d:
                current[sid] = series[i][1]
                i += 1
            indices[sid] = i
        out.append((d, sum(current.values())))
    return out


def user_traffic_growth_days(
    servers_map: dict[int, list[tuple[date, int]]],
) -> frozenset[date]:
    """UTC-календарные дни, когда суммарный трафик вырос относительно предыдущего дня."""

    pairs = cumulative_traffic_by_calendar_days(servers_map)
    if not pairs:
        return frozenset()
    growth: set[date] = set()
    prev = 0
    for d, cum in pairs:
        if cum > prev:
            growth.add(d)
        prev = cum
    return frozenset(growth)


def user_traffic_grew_on_day(
    servers_map: dict[int, list[tuple[date, int]]],
    day: date,
) -> bool:
    """Рост суммарного трафика в ``day`` относительно предыдущего календарного дня."""

    return day in user_traffic_growth_days(servers_map)


def user_has_traffic_ever(servers_map: dict[int, list[tuple[date, int]]]) -> bool:
    for series in servers_map.values():
        if series and int(series[-1][1] or 0) > 0:
            return True
    return False
