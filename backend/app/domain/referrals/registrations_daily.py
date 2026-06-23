"""Регистрации по календарным дням Europe/Moscow, сгруппированные по реферальным токенам."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import iter_calendar_days, moscow_today
from app.domain.models.referral_links import (
    ReferralTokenRegistrationsDailySeries,
    ReferralTokensRegistrationsDailySummary,
    ReferralTrafficRegistrationsDailySummary,
)
from app.domain.users.stats_qualification import user_counts_in_admin_stats
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


async def referral_traffic_registrations_daily(
    session: AsyncSession,
    *,
    days: int,
) -> ReferralTrafficRegistrationsDailySummary:
    """Регистрации по дням МСК с разбивкой по источникам трафика."""
    span = max(1, min(int(days), 366))
    today = moscow_today()
    start = today - timedelta(days=span - 1)
    dates = iter_calendar_days(start, today)

    stats_user = user_counts_in_admin_stats(User)
    reg_msk_day = cast(func.timezone("Europe/Moscow", User.registered_at), Date)

    is_direct = User.referral_link_id.is_(None)
    is_channel = User.referral_link_id.is_not(None) & ReferralLink.owner_user_id.is_(None)
    is_user_referral = User.referral_link_id.is_not(None) & ReferralLink.owner_user_id.is_not(None)
    with_tg = User.telegram_id.is_not(None)
    without_tg = User.telegram_id.is_(None)

    count_rows = (
        await session.execute(
            select(
                reg_msk_day.label("reg_day"),
                func.count().filter(is_direct).label("direct"),
                func.count().filter(is_direct, with_tg).label("direct_bot"),
                func.count().filter(is_direct, without_tg).label("direct_site"),
                func.count().filter(is_channel).label("channel_links"),
                func.count().filter(is_user_referral).label("user_referrals"),
            )
            .select_from(User)
            .outerjoin(ReferralLink, User.referral_link_id == ReferralLink.id)
            .where(
                stats_user,
                User.registered_at.is_not(None),
                reg_msk_day >= start,
                reg_msk_day <= today,
            )
            .group_by(reg_msk_day),
        )
    ).all()

    by_day: dict[date, tuple[int, int, int, int, int]] = {}
    for reg_day, direct, direct_bot, direct_site, channel_links, user_referrals in count_rows:
        if reg_day is None:
            continue
        by_day[reg_day] = (
            int(direct or 0),
            int(direct_bot or 0),
            int(direct_site or 0),
            int(channel_links or 0),
            int(user_referrals or 0),
        )

    direct_series: list[int] = []
    direct_bot_series: list[int] = []
    direct_site_series: list[int] = []
    channel_series: list[int] = []
    user_ref_series: list[int] = []
    total_series: list[int] = []

    for d in dates:
        direct, direct_bot, direct_site, channel_links, user_referrals = by_day.get(
            d,
            (0, 0, 0, 0, 0),
        )
        direct_series.append(direct)
        direct_bot_series.append(direct_bot)
        direct_site_series.append(direct_site)
        channel_series.append(channel_links)
        user_ref_series.append(user_referrals)
        total_series.append(direct + channel_links + user_referrals)

    return ReferralTrafficRegistrationsDailySummary(
        dates=dates,
        direct=direct_series,
        direct_bot=direct_bot_series,
        direct_site=direct_site_series,
        channel_links=channel_series,
        user_referrals=user_ref_series,
        total_registrations_by_day=total_series,
    )


async def referral_tokens_registrations_daily(
    session: AsyncSession,
    *,
    days: int,
    min_registrations: int = 10,
) -> ReferralTokensRegistrationsDailySummary:
    """Регистрации по дням МСК для токенов с registrations_count > min_registrations."""
    span = max(1, min(int(days), 366))
    threshold = max(0, int(min_registrations))
    today = moscow_today()
    start = today - timedelta(days=span - 1)
    dates = iter_calendar_days(start, today)

    link_rows = (
        await session.execute(
            select(
                ReferralLink.id,
                ReferralLink.token,
                ReferralLink.registrations_count,
            )
            .where(ReferralLink.registrations_count > threshold)
            .order_by(ReferralLink.registrations_count.desc(), ReferralLink.id.asc()),
        )
    ).all()
    if not link_rows:
        return ReferralTokensRegistrationsDailySummary(
            dates=dates,
            min_registrations=threshold,
        )

    link_ids = [int(r[0]) for r in link_rows]
    reg_msk_day = cast(func.timezone("Europe/Moscow", User.registered_at), Date)

    count_rows = (
        await session.execute(
            select(
                User.referral_link_id,
                reg_msk_day.label("reg_day"),
                func.count().label("cnt"),
            )
            .where(
                User.referral_link_id.in_(link_ids),
                User.registered_at.is_not(None),
                user_counts_in_admin_stats(User),
                reg_msk_day >= start,
                reg_msk_day <= today,
            )
            .group_by(User.referral_link_id, reg_msk_day),
        )
    ).all()

    by_link_day: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for link_id_raw, reg_day, cnt in count_rows:
        if link_id_raw is None or reg_day is None:
            continue
        by_link_day[int(link_id_raw)][reg_day] = int(cnt or 0)

    token_series: list[ReferralTokenRegistrationsDailySeries] = []
    for link_id_raw, token, reg_count in link_rows:
        link_id = int(link_id_raw)
        counts = [int(by_link_day[link_id].get(d, 0)) for d in dates]
        token_series.append(
            ReferralTokenRegistrationsDailySeries(
                referral_link_id=link_id,
                token=str(token),
                registrations_count=int(reg_count or 0),
                registrations_by_day=counts,
            ),
        )

    total_by_day = [
        sum(int(s.registrations_by_day[i]) for s in token_series)
        for i in range(len(dates))
    ]

    return ReferralTokensRegistrationsDailySummary(
        dates=dates,
        min_registrations=threshold,
        total_registrations_by_day=total_by_day,
        tokens=token_series,
    )
