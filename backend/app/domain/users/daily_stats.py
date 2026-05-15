"""Системные дневные метрики: регистрации, активные пользователи, первые подписочные устройства.

Дневной режим — календарные дни UTC (``rpc_users_daily_stats()``). Почасовой — сутки по календарю
Москвы (``rpc_users_hourly_stats``). Поля ``datetime`` в JSON — Москва (``app.core.moscow_api_time``).
"""

from __future__ import annotations

from collections import defaultdict
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


async def daily_payments_expiry_stats(session: AsyncSession) -> list[DailyPaymentsExpiryStatsRow]:
    """Столбчатый график: ``rpc_daily_payments_and_subscription_expirations()`` (UTC-дни)."""

    stmt = text(
        """
        SELECT stats_date, payments_count,
               subscriptions_expired_inactive_count, subscriptions_expired_active_count
        FROM rpc_daily_payments_and_subscription_expirations()
        """,
    )
    raw = (await session.execute(stmt)).all()
    return [
        DailyPaymentsExpiryStatsRow(
            stats_date=row[0],
            payments_count=int(row[1] or 0),
            subscriptions_expired_inactive_count=int(row[2] or 0),
            subscriptions_expired_active_count=int(row[3] or 0),
        )
        for row in raw
    ]


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
