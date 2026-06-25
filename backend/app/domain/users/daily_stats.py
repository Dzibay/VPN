"""Системные дневные метрики: регистрации, активные пользователи, первые подписочные устройства.

Дневной режим — календарные дни Europe/Moscow (``rpc_users_daily_stats()``; трафик по ``traffic_date`` UTC).
Почасовой — сутки по календарю Москвы (``rpc_users_hourly_stats``). Поля ``datetime`` в JSON — Москва.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.time import (
    as_calendar_date,
    ensure_utc,
    iter_calendar_days,
    moscow_date_period_start_utc,
    moscow_today,
    msk_month_bounds,
)
from app.domain.models.users import (
    DailyPaymentsExpiryDayDetailResponse,
    DailyPaymentsExpiryStatsRow,
    PayExpDayDetailGroup,
    PayExpDayDetailGroupKey,
    PayExpDayPaymentItem,
    PayExpDayUserItem,
    UserStatsByDateRow,
    UsersDailyStatsResponse,
)
from app.domain.traffic_daily import (
    active_users_count_by_traffic_day,
    fetch_user_traffic_series,
    traffic_day_span,
    user_has_traffic_ever,
    user_traffic_growth_days,
)
from app.domain.users.stats_qualification import user_counts_in_admin_stats
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


_DAILY_STATS_ROW_SQL = """
        SELECT stats_date, users_count, users_with_traffic_count,
               active_users_count, subscription_devices_users_count,
               users_cumulative_traffic_over_100_mbit_count,
               persistent_traffic_users_count,
               users_with_payment_count, payments_first_count, payments_repeat_count,
               active_users_with_payment_count,
               users_with_active_subscription_count
"""


def _rows_to_stats(rows: list) -> list[UserStatsByDateRow]:
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
            payments_first_count=int(row[8] or 0),
            payments_repeat_count=int(row[9] or 0),
            active_users_with_payment_count=int(row[10] or 0),
            users_with_active_subscription_count=int(row[11] or 0),
        )
        for row in rows
    ]


async def _set_stats_query_limits(session: AsyncSession) -> None:
    """Ограничить время запроса и ожидание lock — иначе пул API исчерпывается."""
    stmt_ms = max(5_000, int(settings.stats_users_daily_query_timeout_seconds) * 1000)
    lock_ms = max(1_000, int(settings.stats_users_daily_lock_timeout_seconds) * 1000)
    await session.execute(text(f"SET LOCAL statement_timeout = '{stmt_ms}ms'"))
    await session.execute(text(f"SET LOCAL lock_timeout = '{lock_ms}ms'"))


async def stats_by_date_merged(
    session: AsyncSession,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[UserStatsByDateRow]:
    """Сводка по датам: единая точка входа rpc_users_daily_stats.

    rpc_users_daily_stats сам выбирает между кэшем (для холодных дней) и
    live-compute (для горячего окна) — звать compute напрямую больше не нужно.
    """
    await _set_stats_query_limits(session)
    params = {"p_from": date_from, "p_to": date_to}
    stmt = text(
        f"""
        {_DAILY_STATS_ROW_SQL}
        FROM rpc_users_daily_stats(:p_from, :p_to)
        ORDER BY stats_date NULLS LAST
        """,
    )
    rows = (await session.execute(stmt, params)).all()
    return _rows_to_stats(rows)


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


async def _day_baseline_from_mv(
    session: AsyncSession,
    *,
    date_before: date,
) -> tuple[int, int, int, int]:
    await _set_stats_query_limits(session)
    stmt = text("SELECT rpc_users_daily_stats_baseline(:p_before) AS payload")
    row = (await session.execute(stmt, {"p_before": date_before})).one()
    raw = row.payload if isinstance(row.payload, dict) else {}
    return (
        int(raw.get("users_count") or 0),
        int(raw.get("users_with_traffic_count") or 0),
        int(raw.get("subscription_devices_users_count") or 0),
        int(raw.get("users_with_payment_count") or 0),
    )


async def users_daily_stats(
    session: AsyncSession,
    *,
    granularity: Literal["day", "hour"] = "day",
    hour_day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
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
    dated = await stats_by_date_merged(session, date_from=date_from, date_to=date_to)
    day_baseline: tuple[int, int, int, int] | None = None
    if date_from is not None:
        try:
            day_baseline = await _day_baseline_from_mv(session, date_before=date_from)
        except Exception:
            day_baseline = None
    return UsersDailyStatsResponse(
        granularity="day",
        hour_day=None,
        stats_by_date=_with_day_period_start(dated),
        day_baseline_users_count=day_baseline[0] if day_baseline else None,
        day_baseline_users_with_traffic_count=day_baseline[1] if day_baseline else None,
        day_baseline_subscription_devices_users_count=day_baseline[2] if day_baseline else None,
        day_baseline_users_with_payment_count=day_baseline[3] if day_baseline else None,
    )


@dataclass(frozen=True)
class DailyPaymentsExpiryStatsBundle:
    rows: list[DailyPaymentsExpiryStatsRow]
    month_min: str | None
    month_max: str | None


def _payments_expiry_month_bounds(
    expiry_dates: set[date],
    pay_dates: set[date],
) -> tuple[str | None, str | None]:
    all_dates = expiry_dates | pay_dates
    if not all_dates:
        return None, None
    d0 = min(all_dates)
    d1 = max(all_dates)
    return f"{d0.year:04d}-{d0.month:02d}", f"{d1.year:04d}-{d1.month:02d}"


async def daily_payments_expiry_stats(
    session: AsyncSession,
    *,
    month: str | None = None,
) -> DailyPaymentsExpiryStatsBundle:
    """Столбчатый график: оплаты (день МСК) и разбивка по ``subscription_until`` (календарь Москвы)."""

    msk_td = moscow_today()
    stats_user = user_counts_in_admin_stats(User)

    elig_raw = (
        await session.execute(
            select(User.id, User.subscription_until).where(
                stats_user,
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
          AND (
              u.telegram_id IS NOT NULL
              OR (
                  u.email IS NOT NULL
                  AND BTRIM(u.email) <> ''
                  AND u.email_verified_at IS NOT NULL
              )
          )
        GROUP BY 1
        """,
    )
    pay_rows = (await session.execute(pay_stmt)).all()
    pay_by: dict[date, int] = {row[0]: int(row[1] or 0) for row in pay_rows if row[0] is not None}

    pay_split_stmt = text(
        """
        WITH pay AS (
            SELECT
                (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS d,
                ROW_NUMBER() OVER (
                    PARTITION BY p.user_id ORDER BY p.created_at ASC, p.id ASC
                ) AS payment_num
            FROM payments p
            INNER JOIN users u ON u.id = p.user_id
            WHERE u.registered_at IS NOT NULL
              AND u.subscription_until IS NOT NULL
              AND (
                  u.telegram_id IS NOT NULL
                  OR (
                      u.email IS NOT NULL
                      AND BTRIM(u.email) <> ''
                      AND u.email_verified_at IS NOT NULL
                  )
              )
        )
        SELECT
            d,
            COUNT(*) FILTER (WHERE payment_num = 1)::bigint AS first_n,
            COUNT(*) FILTER (WHERE payment_num > 1)::bigint AS repeat_n
        FROM pay
        GROUP BY d
        """,
    )
    pay_split_rows = (await session.execute(pay_split_stmt)).all()
    pay_first_by: dict[date, int] = {
        row[0]: int(row[1] or 0) for row in pay_split_rows if row[0] is not None
    }
    pay_repeat_by: dict[date, int] = {
        row[0]: int(row[2] or 0) for row in pay_split_rows if row[0] is not None
    }

    paid_uids_stmt = text(
        """
        SELECT DISTINCT p.user_id
        FROM payments p
        INNER JOIN users u ON u.id = p.user_id
        WHERE u.registered_at IS NOT NULL
          AND u.subscription_until IS NOT NULL
          AND (
              u.telegram_id IS NOT NULL
              OR (
                  u.email IS NOT NULL
                  AND BTRIM(u.email) <> ''
                  AND u.email_verified_at IS NOT NULL
              )
          )
        """,
    )
    paid_uids = {
        int(row[0])
        for row in (await session.execute(paid_uids_stmt)).all()
        if row[0] is not None
    }
    expiring_paid_by: dict[date, int] = defaultdict(int)
    for su_day, uids in by_su.items():
        expiring_paid_by[su_day] = sum(1 for uid in uids if uid in paid_uids)

    expiry_dates = set(by_su.keys())
    pay_dates = set(pay_by.keys())
    month_min, month_max = _payments_expiry_month_bounds(expiry_dates, pay_dates)

    if month is not None:
        lo, hi = msk_month_bounds(month)
        days = iter_calendar_days(lo, hi)
    else:
        if not expiry_dates and not pay_dates:
            return DailyPaymentsExpiryStatsBundle(rows=[], month_min=month_min, month_max=month_max)
        d0 = min(expiry_dates | pay_dates | {msk_td})
        d1 = max(expiry_dates | pay_dates | {msk_td})
        days = iter_calendar_days(d0, d1)

    days_set = set(days)
    traffic_uids: set[int] = set()
    for su_day, uids in by_su.items():
        if su_day in days_set:
            traffic_uids.update(uids)

    by_user = await fetch_user_traffic_series(
        session,
        user_ids_filter=traffic_uids if traffic_uids else None,
        eligible_users_only=True,
    )

    user_flags: dict[int, tuple[bool, frozenset[date]]] = {}
    bucket_by_day: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0, 0])

    for su_day, uids in by_su.items():
        if su_day not in days_set:
            continue
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

    out: list[DailyPaymentsExpiryStatsRow] = []
    for d in days:
        counts = bucket_by_day.get(d)
        t, s, o, g = tuple(counts) if counts else (0, 0, 0, 0)
        pay_n = int(pay_by.get(d, 0) or 0)
        pay_first_n = int(pay_first_by.get(d, 0) or 0)
        pay_repeat_n = int(pay_repeat_by.get(d, 0) or 0)
        expiring_paid_n = int(expiring_paid_by.get(d, 0) or 0)
        tot_e = t + s + o + g
        out.append(
            DailyPaymentsExpiryStatsRow(
                stats_date=d,
                payments_count=pay_n,
                payments_first_count=pay_first_n,
                payments_repeat_count=pay_repeat_n,
                subscription_expiring_has_payment_count=expiring_paid_n,
                subscription_expiring_total_count=tot_e,
                subscription_expiring_active_today_count=t,
                subscription_expiring_active_on_day_count=s,
                subscription_expiring_has_traffic_count=o,
                subscription_expiring_no_traffic_count=g,
            ),
        )
    return DailyPaymentsExpiryStatsBundle(
        rows=out,
        month_min=month_min,
        month_max=month_max,
    )


_PAY_EXP_GROUP_META: dict[
    PayExpDayDetailGroupKey,
    tuple[str, str],
] = {
    "payments_first": (
        "Оплаты: первая",
        "Первый платёж пользователя за всё время (по дате создания)",
    ),
    "payments_repeat": (
        "Оплаты: повторная",
        "Платёж пользователя, у которого уже была более ранняя оплата",
    ),
    "expiry_no_traffic": (
        "Окончание: без трафика",
        "Подписка истекает в этот день; суммарного трафика не было",
    ),
    "expiry_has_traffic": (
        "Окончание: с трафиком",
        "Истекает в этот день; трафик был, но нет роста ни сегодня, ни в день окончания",
    ),
    "expiry_active_on_day": (
        "Окончание: активные в день окончания",
        "Рост трафика в день окончания, но не в текущий день МСК",
    ),
    "expiry_active_today": (
        "Окончание: активные сегодня (МСК)",
        "Рост суммарного трафика в текущий календарный день Москвы",
    ),
}


def _telegram_username_from_props(props: object) -> str | None:
    if not isinstance(props, dict):
        return None
    uname = props.get("username")
    if isinstance(uname, str):
        uname = uname.strip()
        return uname or None
    return None


def _user_to_pay_exp_item(
    user: User,
    paid_uids: set[int],
    *,
    stats_date: date | None = None,
    paid_on_day_uids: set[int] | None = None,
) -> PayExpDayUserItem:
    uid = int(user.id)
    has_paid = uid in paid_uids
    su = as_calendar_date(user.subscription_until)
    did_not_renew = False
    if stats_date is not None and paid_on_day_uids is not None:
        did_not_renew = (
            has_paid
            and su == stats_date
            and uid not in paid_on_day_uids
        )
    return PayExpDayUserItem(
        user_id=uid,
        email=user.email,
        telegram_id=int(user.telegram_id) if user.telegram_id is not None else None,
        telegram_username=_telegram_username_from_props(user.telegram_properties),
        subscription_until=su,
        has_payments_ever=has_paid,
        did_not_renew=did_not_renew,
    )


def _classify_expiring_user(
    uid: int,
    su_day: date,
    msk_td: date,
    by_user: dict,
    user_flags: dict[int, tuple[bool, frozenset[date]]],
) -> PayExpDayDetailGroupKey:
    sm = by_user.get(uid)
    if not sm or not any(series for series in sm.values()):
        return "expiry_no_traffic"
    if uid not in user_flags:
        user_flags[uid] = (
            user_has_traffic_ever(sm),
            user_traffic_growth_days(sm),
        )
    has_tr, growth = user_flags[uid]
    if msk_td in growth:
        return "expiry_active_today"
    if su_day in growth:
        return "expiry_active_on_day"
    if has_tr:
        return "expiry_has_traffic"
    return "expiry_no_traffic"


async def daily_payments_expiry_day_detail(
    session: AsyncSession,
    *,
    day: date,
) -> DailyPaymentsExpiryDayDetailResponse:
    """Списки пользователей и платежей за один календарный день Europe/Moscow."""

    msk_td = moscow_today()
    stats_user = user_counts_in_admin_stats(User)

    elig_raw = (
        await session.execute(
            select(User.id, User.subscription_until).where(
                stats_user,
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

    paid_uids_stmt = text(
        """
        SELECT DISTINCT p.user_id
        FROM payments p
        INNER JOIN users u ON u.id = p.user_id
        WHERE u.registered_at IS NOT NULL
          AND u.subscription_until IS NOT NULL
          AND (
              u.telegram_id IS NOT NULL
              OR (
                  u.email IS NOT NULL
                  AND BTRIM(u.email) <> ''
                  AND u.email_verified_at IS NOT NULL
              )
          )
        """,
    )
    paid_uids = {
        int(row[0])
        for row in (await session.execute(paid_uids_stmt)).all()
        if row[0] is not None
    }

    pay_detail_stmt = text(
        """
        WITH pay AS (
            SELECT
                p.id AS payment_id,
                p.user_id,
                p.amount,
                p.provider,
                p.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY p.user_id ORDER BY p.created_at ASC, p.id ASC
                ) AS payment_num
            FROM payments p
            INNER JOIN users u ON u.id = p.user_id
            WHERE u.registered_at IS NOT NULL
              AND u.subscription_until IS NOT NULL
              AND (
                  u.telegram_id IS NOT NULL
                  OR (
                      u.email IS NOT NULL
                      AND BTRIM(u.email) <> ''
                      AND u.email_verified_at IS NOT NULL
                  )
              )
        )
        SELECT payment_id, user_id, amount, provider, created_at, payment_num
        FROM pay
        WHERE (created_at AT TIME ZONE 'Europe/Moscow')::date = :day
        ORDER BY created_at ASC, payment_id ASC
        """,
    )
    pay_rows = (await session.execute(pay_detail_stmt, {"day": day})).all()
    paid_on_day_uids = {
        int(row[1]) for row in pay_rows if row[1] is not None
    }

    by_user = await fetch_user_traffic_series(
        session,
        user_ids_filter=set(by_su.get(day, [])),
        eligible_users_only=True,
    )
    user_flags: dict[int, tuple[bool, frozenset[date]]] = {}

    expiry_buckets: dict[PayExpDayDetailGroupKey, list[int]] = defaultdict(list)
    for uid in by_su.get(day, []):
        bucket = _classify_expiring_user(uid, day, msk_td, by_user, user_flags)
        expiry_buckets[bucket].append(uid)

    user_ids_needed: set[int] = set()
    for uid in by_su.get(day, []):
        user_ids_needed.add(uid)
    for row in pay_rows:
        if row[1] is not None:
            user_ids_needed.add(int(row[1]))

    users_by_id: dict[int, User] = {}
    if user_ids_needed:
        users_raw = (
            await session.scalars(select(User).where(User.id.in_(user_ids_needed)))
        ).all()
        users_by_id = {int(u.id): u for u in users_raw}

    payments_first: list[PayExpDayPaymentItem] = []
    payments_repeat: list[PayExpDayPaymentItem] = []
    for row in pay_rows:
        payment_id = int(row[0])
        uid = int(row[1])
        user = users_by_id.get(uid)
        uname = _telegram_username_from_props(user.telegram_properties) if user else None
        item = PayExpDayPaymentItem(
            payment_id=payment_id,
            user_id=uid,
            email=user.email if user else None,
            telegram_id=int(user.telegram_id) if user and user.telegram_id is not None else None,
            telegram_username=uname,
            amount_rub=row[2],
            provider=str(row[3] or ""),
            is_first_payment=int(row[5] or 0) == 1,
            payment_at=ensure_utc(row[4]),
        )
        if item.is_first_payment:
            payments_first.append(item)
        else:
            payments_repeat.append(item)

    def expiry_users(key: PayExpDayDetailGroupKey) -> list[PayExpDayUserItem]:
        uids = sorted(expiry_buckets.get(key, []))
        out: list[PayExpDayUserItem] = []
        for uid in uids:
            user = users_by_id.get(uid)
            if user is None:
                continue
            out.append(
                _user_to_pay_exp_item(
                    user,
                    paid_uids,
                    stats_date=day,
                    paid_on_day_uids=paid_on_day_uids,
                ),
            )
        out.sort(key=lambda u: (not u.did_not_renew, u.user_id))
        return out

    raw_groups: list[tuple[PayExpDayDetailGroupKey, list[PayExpDayUserItem], list[PayExpDayPaymentItem]]] = [
        ("payments_first", [], payments_first),
        ("payments_repeat", [], payments_repeat),
        ("expiry_no_traffic", expiry_users("expiry_no_traffic"), []),
        ("expiry_has_traffic", expiry_users("expiry_has_traffic"), []),
        ("expiry_active_on_day", expiry_users("expiry_active_on_day"), []),
        ("expiry_active_today", expiry_users("expiry_active_today"), []),
    ]

    groups: list[PayExpDayDetailGroup] = []
    for key, users, payments in raw_groups:
        count = len(payments) if payments else len(users)
        if count <= 0:
            continue
        title, hint = _PAY_EXP_GROUP_META[key]
        paid_users_count = 0
        did_not_renew_count = 0
        if users:
            paid_users_count = sum(1 for u in users if u.has_payments_ever)
            did_not_renew_count = sum(1 for u in users if u.did_not_renew)
        groups.append(
            PayExpDayDetailGroup(
                key=key,
                title=title,
                hint=hint,
                count=count,
                paid_users_count=paid_users_count,
                did_not_renew_count=did_not_renew_count,
                users=users,
                payments=payments,
            ),
        )

    return DailyPaymentsExpiryDayDetailResponse(stats_date=day, groups=groups)


async def count_users_with_subscription_device(
    session: AsyncSession,
    referral_link_id: int | None,
) -> int:
    """Число пользователей с хотя бы одной записью в ``subscription_devices``."""

    stmt = select(func.count(func.distinct(SubscriptionDevice.user_id))).select_from(
        SubscriptionDevice,
    ).join(User, User.id == SubscriptionDevice.user_id).where(
        user_counts_in_admin_stats(User),
    )
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return int(await session.scalar(stmt) or 0)


async def active_users_count_for_utc_date(
    session: AsyncSession,
    cal_day: date,
    referral_link_id: int | None,
) -> int:
    """«Активные» за календарный день UTC по ``traffic_date`` (воронка рефералов)."""

    user_filter_sql = ""
    params: dict[str, object] = {"cal_day": cal_day}
    if referral_link_id is not None:
        user_filter_sql = "AND u.referral_link_id = :referral_link_id"
        params["referral_link_id"] = referral_link_id

    stmt = text(
        f"""
        WITH qualified AS (
            SELECT u.id
            FROM users u
            WHERE (
                u.telegram_id IS NOT NULL
                OR (
                    u.email IS NOT NULL
                    AND BTRIM(u.email) <> ''
                    AND u.email_verified_at IS NOT NULL
                )
            )
            {user_filter_sql}
        ),
        traffic_cum AS (
            SELECT
                t.user_id,
                t.server_id,
                MAX(
                    CASE
                        WHEN t.traffic_date <= :cal_day
                            THEN t.up_bytes + t.down_bytes
                    END
                )::bigint AS cum_d,
                MAX(
                    CASE
                        WHEN t.traffic_date < :cal_day
                            THEN t.up_bytes + t.down_bytes
                    END
                )::bigint AS cum_prev
            FROM user_server_traffic t
            INNER JOIN qualified q ON q.id = t.user_id
            WHERE t.traffic_date <= :cal_day
            GROUP BY t.user_id, t.server_id
        ),
        user_totals AS (
            SELECT
                user_id,
                COALESCE(SUM(cum_d), 0)::bigint AS total_d,
                COALESCE(SUM(cum_prev), 0)::bigint AS total_prev
            FROM traffic_cum
            GROUP BY user_id
        )
        SELECT COUNT(*)::bigint
        FROM user_totals
        WHERE total_d > total_prev
        """,
    )
    return int(await session.scalar(stmt, params) or 0)
