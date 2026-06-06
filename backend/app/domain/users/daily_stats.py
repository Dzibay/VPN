"""Системные дневные метрики: регистрации, активные пользователи, первые подписочные устройства.

Дневной режим — календарные дни Europe/Moscow (``rpc_users_daily_stats()``; трафик по ``traffic_date`` UTC).
Почасовой — сутки по календарю Москвы (``rpc_users_hourly_stats``). Поля ``datetime`` в JSON — Москва.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import (
    as_calendar_date,
    ensure_utc,
    iter_calendar_days,
    moscow_date_period_start_utc,
    moscow_today,
    msk_month_bounds,
)
from app.domain.models.users import (
    DailyPaymentsExpiryStatsRow,
    UserStatsByDateRow,
    UsersDailyStatsResponse,
)
from app.domain.traffic_daily import (
    active_users_count_by_traffic_day,
    fetch_user_traffic_series,
    user_has_traffic_ever,
    user_traffic_growth_days,
)
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User

def _with_day_period_start(rows: list[UserStatsByDateRow]) -> list[UserStatsByDateRow]:
    """Для дневного режима задаёт ``period_start_utc`` — полночь ``stats_date`` по Europe/Moscow (UTC instant)."""

    out: list[UserStatsByDateRow] = []
    for r in rows:
        if r.stats_date is None:
            out.append(r)
            continue
        start = moscow_date_period_start_utc(r.stats_date)
        out.append(r.model_copy(update={"period_start_utc": start}))
    return out


async def stats_by_date_merged(session: AsyncSession) -> list[UserStatsByDateRow]:
    """Сводка по датам через PostgreSQL ``rpc_users_daily_stats()`` (см. ``database/rpc/users_daily_stats.sql``).

    Строка без ``stats_date`` — пользователи без ``registered_at`` (в конце набора).
    Дневные ``users_count`` — прирост по дню регистрации (МСК) для всех с ``registered_at``,
    без фильтра по ``subscription_until``.
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
    """Сводка для эндпоинта ``/users/daily-stats`` (дни МСК или 24 часа календарного дня МСК)."""

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
                ps = ensure_utc(ps)
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


async def daily_payments_expiry_stats(
    session: AsyncSession,
    *,
    month: str | None = None,
) -> list[DailyPaymentsExpiryStatsRow]:
    """Столбчатый график: оплаты (день МСК) и разбивка по ``subscription_until`` (календарь Москвы)."""

    msk_td = moscow_today()

    elig_raw = (
        await session.execute(
            select(User.id, User.subscription_until).where(
                User.registered_at.is_not(None),
                User.subscription_until.isnot(None),
            ),
        )
    ).all()
    by_su: dict[date, list[int]] = defaultdict(list)
    for uid_raw, su_raw in elig_raw:
        su = as_calendar_date(su_raw)
        if su is None:
            continue
        by_su[su].append(int(uid_raw))

    pay_stmt = text(
        """
        SELECT (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS d, COUNT(*)::bigint AS n
        FROM payments p
        INNER JOIN users u ON u.id = p.user_id
        WHERE u.registered_at IS NOT NULL
          AND u.subscription_until IS NOT NULL
        GROUP BY 1
        """,
    )
    pay_rows = (await session.execute(pay_stmt)).all()
    pay_by: dict[date, int] = {row[0]: int(row[1] or 0) for row in pay_rows if row[0] is not None}

    by_user = await fetch_user_traffic_series(session, eligible_users_only=True)

    user_flags: dict[int, tuple[bool, frozenset[date]]] = {}
    bucket_by_day: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0, 0])

    for su_day, uids in by_su.items():
        for uid in uids:
            sm = by_user.get(uid)
            if not sm or not any(series for series in sm.values()):
                bucket_by_day[su_day][3] += 1
                continue
            if uid not in user_flags:
                user_flags[uid] = (
                    user_has_traffic_ever(sm),
                    user_traffic_growth_days(sm),
                )
            has_tr, growth = user_flags[uid]
            if msk_td in growth:
                bucket_by_day[su_day][0] += 1
            elif su_day in growth:
                bucket_by_day[su_day][1] += 1
            elif has_tr:
                bucket_by_day[su_day][2] += 1
            else:
                bucket_by_day[su_day][3] += 1

    expiry_dates = set(by_su.keys())
    pay_dates = set(pay_by.keys())

    if month is not None:
        lo, hi = msk_month_bounds(month)
        days = iter_calendar_days(lo, hi)
    else:
        if not expiry_dates and not pay_dates:
            return []
        d0 = min(expiry_dates | pay_dates | {msk_td})
        d1 = max(expiry_dates | pay_dates | {msk_td})
        days = iter_calendar_days(d0, d1)

    out: list[DailyPaymentsExpiryStatsRow] = []
    for d in days:
        counts = bucket_by_day.get(d)
        t, s, o, g = tuple(counts) if counts else (0, 0, 0, 0)
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
    """Число пользователей с хотя бы одной записью в ``subscription_devices``."""

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
    """«Активные» за календарный день UTC по ``traffic_date`` (воронка рефералов)."""

    filt: set[int] | None = None
    if referral_link_id is not None:
        ids_raw = (
            await session.scalars(
                select(User.id).where(User.referral_link_id == referral_link_id),
            )
        ).all()
        filt = {int(i) for i in ids_raw}
    series = await fetch_user_traffic_series(session, user_ids_filter=filt)
    counts = active_users_count_by_traffic_day(series, day_list=[cal_day])
    return int(counts.get(cal_day, 0) or 0)
