"""Системные дневные метрики: регистрации, активные пользователи, первые подписочные устройства.

Дневной режим — календарные дни UTC (``rpc_users_daily_stats()``). Почасовой — сутки по календарю
Москвы (``rpc_users_hourly_stats``). Поля ``datetime`` в JSON — Москва (``app.core.moscow_api_time``).
"""

from __future__ import annotations

from collections import defaultdict
import bisect
import calendar
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import as_calendar_date
from app.domain.models.users import (
    DailyPaymentsExpiryStatsRow,
    UserStatsByDateRow,
    UsersDailyStatsResponse,
)
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


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _with_day_period_start(rows: list[UserStatsByDateRow]) -> list[UserStatsByDateRow]:
    """Для дневного режима задаёт ``period_start_utc`` полуночью UTC для строк с ``stats_date``."""

    out: list[UserStatsByDateRow] = []
    for r in rows:
        if r.stats_date is None:
            out.append(r)
            continue
        start = datetime.combine(r.stats_date, time.min, tzinfo=timezone.utc)
        out.append(r.model_copy(update={"period_start_utc": start}))
    return out


async def stats_by_date_merged(session: AsyncSession) -> list[UserStatsByDateRow]:
    """Сводка по датам через PostgreSQL ``rpc_users_daily_stats()`` (см. ``database/rpc/users_daily_stats.sql``).

    Строка без даты регистрации (``stats_date IS NULL``) — в конце набора, если есть такие пользователи.
    """
    stmt = text(
        """
        SELECT stats_date, users_count, users_with_traffic_count,
               active_users_count, subscription_devices_users_count,
               users_cumulative_traffic_over_100_mbit_count,
               persistent_traffic_users_count,
               users_with_payment_count, active_users_with_payment_count,
               users_with_active_subscription_count
        FROM rpc_users_daily_stats()
        """,
    )
    rows = (await session.execute(stmt)).all()
    return [
        UserStatsByDateRow(
            stats_date=row[0],
            period_start_utc=None,
            users_count=int(row[1] or 0),
            users_with_traffic_count=int(row[2] or 0),
            active_users_count=int(row[3] or 0),
            subscription_devices_users_count=int(row[4] or 0),
            users_cumulative_traffic_over_100_mbit_count=int(row[5] or 0),
            persistent_traffic_users_count=int(row[6] or 0),
            users_with_payment_count=int(row[7] or 0),
            active_users_with_payment_count=int(row[8] or 0),
            users_with_active_subscription_count=int(row[9] or 0),
        )
        for row in rows
    ]


def _hour_extras_from_first_rpc_row(row: object | None) -> tuple[int, int, int, int]:
    """Дублирующиеся поля RPC на каждой строке — достаточно первой."""

    if row is None or len(row) < 9:
        return (0, 0, 0, 0)
    return (
        int(row[5] or 0),
        int(row[6] or 0),
        int(row[7] or 0),
        int(row[8] or 0),
    )


async def users_daily_stats(
    session: AsyncSession,
    *,
    granularity: Literal["day", "hour"] = "day",
    hour_day: date | None = None,
) -> UsersDailyStatsResponse:
    """Сводка для эндпоинта ``/users/daily-stats`` (дни UTC или 24 часа календарного дня МСК)."""

    if granularity == "hour":
        if hour_day is None:
            raise ValueError("hour_day обязателен при granularity=hour")
        stmt = text(
            """
            SELECT period_start_utc, users_count, users_with_traffic_count,
                   active_users_count, subscription_devices_users_count,
                   baseline_users_count, baseline_users_with_traffic_count,
                   baseline_subscription_devices_users_count, undated_users_count
            FROM rpc_users_hourly_stats(:hour_day)
            """,
        )
        raw_rows = (await session.execute(stmt, {"hour_day": hour_day})).all()
        hb_users, hb_traffic, hb_devices, undated_n = _hour_extras_from_first_rpc_row(
            raw_rows[0] if raw_rows else None,
        )
        stats_rows: list[UserStatsByDateRow] = []
        for row in raw_rows:
            ps = row[0]
            if ps is not None:
                ps = _naive_utc(ps)
            stats_rows.append(
                UserStatsByDateRow(
                    stats_date=None,
                    period_start_utc=ps,
                    users_count=int(row[1] or 0),
                    users_with_traffic_count=int(row[2] or 0),
                    active_users_count=int(row[3] or 0),
                    subscription_devices_users_count=int(row[4] or 0),
                    users_cumulative_traffic_over_100_mbit_count=0,
                    persistent_traffic_users_count=0,
                    users_with_payment_count=0,
                    active_users_with_payment_count=0,
                    users_with_active_subscription_count=0,
                ),
            )
        return UsersDailyStatsResponse(
            granularity="hour",
            hour_day=hour_day,
            stats_by_date=stats_rows,
            hour_baseline_users_count=hb_users,
            hour_baseline_users_with_traffic_count=hb_traffic,
            hour_baseline_subscription_devices_users_count=hb_devices,
            hour_undated_users_count=undated_n,
        )
    dated = await stats_by_date_merged(session)
    return UsersDailyStatsResponse(
        granularity="day",
        hour_day=None,
        stats_by_date=_with_day_period_start(dated),
    )


def _utc_month_bounds(month: str) -> tuple[date, date]:
    """Первый и последний календарный день месяца UTC (YYYY-MM)."""
    s = month.strip()
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError("month: ожидается формат YYYY-MM")
    try:
        y = int(parts[0], 10)
        mo = int(parts[1], 10)
    except ValueError as e:
        raise ValueError("month: неверные числа в YYYY-MM") from e
    if y < 1970 or y > 2100 or mo < 1 or mo > 12:
        raise ValueError("month: недопустимый год или месяц")
    first = date(y, mo, 1)
    last = date(y, mo, calendar.monthrange(y, mo)[1])
    return first, last


def _utc_today_date() -> date:
    return datetime.now(timezone.utc).date()


def _iter_calendar_days(d0: date, d1: date) -> list[date]:
    out: list[date] = []
    d = d0
    while d <= d1:
        out.append(d)
        d += timedelta(days=1)
    return out


def _subscription_until_as_date(val: object) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc).date() if val.tzinfo else val.date()
    if isinstance(val, date):
        return val
    return as_calendar_date(val)


def _bytes_at_or_before(series: list[tuple[date, int]], end: date) -> int:
    if not series:
        return 0
    dates = [t[0] for t in series]
    i = bisect.bisect_right(dates, end) - 1
    if i < 0:
        return 0
    return int(series[i][1] or 0)


def _user_bytes_totals_at(
    servers_map: dict[int, list[tuple[date, int]]],
    end: date,
) -> int:
    return sum(_bytes_at_or_before(series, end) for series in servers_map.values())


def _user_active_on_expiry_day(
    servers_map: dict[int, list[tuple[date, int]]],
    expiry_day: date,
) -> bool:
    prev_day = expiry_day - timedelta(days=1)
    return _user_bytes_totals_at(servers_map, expiry_day) > _user_bytes_totals_at(
        servers_map,
        prev_day,
    )


def _user_has_traffic_ever(servers_map: dict[int, list[tuple[date, int]]]) -> bool:
    for series in servers_map.values():
        if series and int(series[-1][1] or 0) > 0:
            return True
    return False


async def daily_payments_expiry_stats(
    session: AsyncSession,
    *,
    month: str | None = None,
) -> list[DailyPaymentsExpiryStatsRow]:
    """Столбчатый график: оплаты и разбивка пользователей по ``subscription_until`` (UTC-календарь).

    Для каждого ``stats_date`` считаются только пользователи с
    ``subscription_until = stats_date`` (и ``registered_at`` задан).
    Каждый такой пользователь попадает ровно в одну из четырёх групп (приоритет сверху вниз):

    1. «Активные сегодня» — только если ``stats_date`` — текущий календарный день UTC и в этот день
       вырос суммарный трафик (как ``active_users_count`` в ``rpc_users_daily_stats``).
    2. «Активные в день окончания» — рост суммарного трафика в ``stats_date``, но день не «сегодня» UTC.
    3. «С трафиком» — иначе, если когда-либо был ненулевой суммарный трафик по данным ``user_server_traffic``.
    4. «Без трафика» — иначе.

    При ``month=YYYY-MM`` возвращаются **все** календарные дни этого месяца UTC (в т.ч. без событий).
    Без ``month`` — плотный ряд от минимальной даты среди окончаний/оплат до максимальной и сегодня UTC.
    """

    utc_td = _utc_today_date()

    elig_raw = (
        await session.execute(
            select(User.id, User.subscription_until).where(
                User.registered_at.isnot(None),
                User.subscription_until.isnot(None),
            ),
        )
    ).all()
    eligible: list[tuple[int, date]] = []
    for uid_raw, su_raw in elig_raw:
        su = _subscription_until_as_date(su_raw)
        if su is None:
            continue
        eligible.append((int(uid_raw), su))

    by_su: dict[date, list[int]] = defaultdict(list)
    for uid, su in eligible:
        by_su[su].append(uid)

    pay_stmt = text(
        """
        SELECT (p.created_at AT TIME ZONE 'UTC')::date AS d, COUNT(*)::bigint AS n
        FROM payments p
        INNER JOIN users u ON u.id = p.user_id
        WHERE u.registered_at IS NOT NULL
          AND u.subscription_until IS NOT NULL
        GROUP BY 1
        """,
    )
    pay_rows = (await session.execute(pay_stmt)).all()
    pay_by: dict[date, int] = {row[0]: int(row[1] or 0) for row in pay_rows if row[0] is not None}

    tr_stmt = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
        )
        .select_from(UserServerTraffic)
        .join(User, User.id == UserServerTraffic.user_id)
        .where(
            User.registered_at.isnot(None),
            User.subscription_until.isnot(None),
        )
        .order_by(
            UserServerTraffic.user_id.asc(),
            UserServerTraffic.server_id.asc(),
            UserServerTraffic.traffic_date.asc(),
        )
    )
    tr_raw = (await session.execute(tr_stmt)).all()
    by_user: dict[int, dict[int, list[tuple[date, int]]]] = defaultdict(
        lambda: defaultdict(list),
    )
    for uid_raw, sid_raw, td_raw, tot_raw in tr_raw:
        cal = as_calendar_date(td_raw)
        if cal is None:
            continue
        tot = int(tot_raw or 0)
        if tot < 0:
            tot = 0
        uid = int(uid_raw)
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

    ever_cache: dict[int, bool] = {}

    def ever_positive(uid: int, sm: dict[int, list[tuple[date, int]]]) -> bool:
        if uid not in ever_cache:
            ever_cache[uid] = _user_has_traffic_ever(sm)
        return ever_cache[uid]

    expiry_dates = set(by_su.keys())
    pay_dates = set(pay_by.keys())

    if month is not None:
        lo, hi = _utc_month_bounds(month)
        days = _iter_calendar_days(lo, hi)
    else:
        if not expiry_dates and not pay_dates:
            return []
        d0 = min(expiry_dates | pay_dates | {utc_td})
        d1 = max(expiry_dates | pay_dates | {utc_td})
        days = _iter_calendar_days(d0, d1)

    bucket_by_day: dict[date, tuple[int, int, int, int]] = {}
    for su_day, uids in by_su.items():
        n_today = n_day = n_traffic = n_none = 0
        for uid in uids:
            sm = by_user.get(uid)
            if not sm or not any(series for series in sm.values()):
                n_none += 1
                continue
            active_here = _user_active_on_expiry_day(sm, su_day)
            has_tr = ever_positive(uid, sm)
            if active_here and su_day == utc_td:
                n_today += 1
            elif active_here:
                n_day += 1
            elif has_tr:
                n_traffic += 1
            else:
                n_none += 1
        bucket_by_day[su_day] = (n_today, n_day, n_traffic, n_none)

    out: list[DailyPaymentsExpiryStatsRow] = []
    for d in days:
        t, s, o, g = bucket_by_day.get(d, (0, 0, 0, 0))
        pay_n = int(pay_by.get(d, 0) or 0)
        tot_e = t + s + o + g
        out.append(
            DailyPaymentsExpiryStatsRow(
                stats_date=d,
                payments_count=pay_n,
                subscription_expiring_total_count=tot_e,
                subscription_expiring_active_today_count=t,
                subscription_expiring_active_on_day_count=s,
                subscription_expiring_has_traffic_count=o,
                subscription_expiring_no_traffic_count=g,
            ),
        )
    return out


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
