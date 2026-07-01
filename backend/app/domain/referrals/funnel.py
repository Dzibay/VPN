"""Воронка реферальной ссылки: клики → регистрации → пользователи с трафиком/устройствами/активные.

Используется в админ-эндпоинте сводки по выбранной ссылке (или по всему сайту, если
``referral_link_id is None``). Все сводные числа неотрицательны: невалидные значения из
агрегатов SQL приводятся к 0.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.time import utc_today
from app.domain.referrals.errors import ReferralLinkGroupNotFoundError
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.domain.users.daily_stats import (
    active_users_count_for_utc_date,
    count_users_with_subscription_device,
)
from app.domain.users.stats_qualification import user_counts_in_admin_stats
from app.domain.tenant.admin_project_scope import (
    admin_project_id,
    merge_project_sql_params,
    project_scope_clause,
    user_table_project_filter_sql,
)
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.referral_link_group import ReferralLinkGroup
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User


def _user_scope_filter():
    return project_scope_clause(User)


def _nz_metric(v: object) -> int:
    """Нормализатор: невалидное/отрицательное → 0, остальное — ``int``."""
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, n)


async def referral_funnel_compute(
    session: AsyncSession,
    referral_link_id: int | None,
    referral_link_group_id: int | None,
    _cfg: object,
):
    """Сводка воронки по ссылке, группе токенов или по всем пользователям сайта."""
    from app.domain.models.referral_links import ReferralFunnelSummary

    latest = user_server_traffic_latest_subquery()
    per_user_traffic = (
        select(
            latest.c.user_id.label("uid"),
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            ).label("tot"),
        )
        .group_by(latest.c.user_id)
        .having(
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            )
            > 0,
        )
        .subquery()
    )
    today = utc_today()

    if referral_link_group_id is not None:
        group = await session.get(ReferralLinkGroup, referral_link_group_id)
        if group is None:
            raise ReferralLinkGroupNotFoundError
        pid = admin_project_id()
        if pid is not None and int(group.project_id) != pid:
            raise ReferralLinkGroupNotFoundError
        link_ids = list(
            (
                await session.scalars(
                    select(ReferralLink.id).where(
                        ReferralLink.group_id == referral_link_group_id,
                    ),
                )
            ).all(),
        )
        if not link_ids:
            return ReferralFunnelSummary(
                clicks_total=0,
                registrations_total=0,
                users_with_traffic=0,
                users_with_subscription_device=0,
                users_with_payment=0,
                active_users_today_utc=0,
            )
        clicks_total_raw = await session.scalar(
            select(func.coalesce(func.sum(ReferralLink.clicks_count), 0)).where(
                ReferralLink.id.in_(link_ids),
            ),
        )
        link_filter = User.referral_link_id.in_(link_ids)
        user_stats = user_counts_in_admin_stats(User)
        scope = _user_scope_filter()
        reg_where = [link_filter, user_stats]
        if scope is not None:
            reg_where.append(scope)
        registrations_total_raw = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(*reg_where),
        )
        users_with_traffic_raw = await session.scalar(
            select(func.count())
            .select_from(per_user_traffic)
            .join(User, User.id == per_user_traffic.c.uid)
            .where(*reg_where),
        )
        with_dev = await _count_users_with_subscription_device_for_links(session, link_ids)
        with_payment = await _count_users_with_payment_for_links(session, link_ids)
        active_today = await _active_users_count_for_utc_date_by_links(session, today, link_ids)
        return ReferralFunnelSummary(
            clicks_total=_nz_metric(clicks_total_raw),
            registrations_total=_nz_metric(registrations_total_raw),
            users_with_traffic=_nz_metric(users_with_traffic_raw),
            users_with_subscription_device=_nz_metric(with_dev),
            users_with_payment=_nz_metric(with_payment),
            active_users_today_utc=_nz_metric(active_today),
        )

    if referral_link_id is not None:
        row = (
            await session.scalars(
                select(ReferralLink).where(ReferralLink.id == referral_link_id).limit(1),
            )
        ).first()
        if row is None:
            raise NotFoundError("Реферальная ссылка не найдена")
        pid = admin_project_id()
        if pid is not None and int(row.project_id) != pid:
            raise NotFoundError("Реферальная ссылка не найдена")
        user_stats = user_counts_in_admin_stats(User)
        scope = _user_scope_filter()
        reg_where = [User.referral_link_id == referral_link_id, user_stats]
        if scope is not None:
            reg_where.append(scope)
        registrations_total_raw = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(*reg_where),
        )
        users_with_traffic_raw = await session.scalar(
            select(func.count())
            .select_from(per_user_traffic)
            .join(User, User.id == per_user_traffic.c.uid)
            .where(*reg_where),
        )
        today = utc_today()
        with_dev = await count_users_with_subscription_device(session, referral_link_id)
        with_payment = await _count_users_with_payment(session, referral_link_id)
        active_today = await active_users_count_for_utc_date(session, today, referral_link_id)
        return ReferralFunnelSummary(
            clicks_total=_nz_metric(row.clicks_count),
            registrations_total=_nz_metric(registrations_total_raw),
            users_with_traffic=_nz_metric(users_with_traffic_raw),
            users_with_subscription_device=_nz_metric(with_dev),
            users_with_payment=_nz_metric(with_payment),
            active_users_today_utc=_nz_metric(active_today),
        )

    user_stats = user_counts_in_admin_stats(User)
    scope = _user_scope_filter()
    site_where = [user_stats]
    if scope is not None:
        site_where.append(scope)
    registrations_total_raw = await session.scalar(
        select(func.count()).select_from(User).where(*site_where),
    )
    users_with_traffic_raw = await session.scalar(
        select(func.count())
        .select_from(per_user_traffic)
        .join(User, User.id == per_user_traffic.c.uid)
        .where(*site_where),
    )
    today = utc_today()
    with_dev = await count_users_with_subscription_device(session, None)
    with_payment = await _count_users_with_payment(session, None)
    active_today = await active_users_count_for_utc_date(session, today, None)

    return ReferralFunnelSummary(
        clicks_total=None,
        registrations_total=_nz_metric(registrations_total_raw),
        users_with_traffic=_nz_metric(users_with_traffic_raw),
        users_with_subscription_device=_nz_metric(with_dev),
        users_with_payment=_nz_metric(with_payment),
        active_users_today_utc=_nz_metric(active_today),
    )


async def _count_users_with_payment(
    session: AsyncSession,
    referral_link_id: int | None,
) -> int:
    stmt = (
        select(func.count(func.distinct(Payment.user_id)))
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .where(
            Payment.user_id.is_not(None),
            user_counts_in_admin_stats(User),
        )
    )
    scope = _user_scope_filter()
    if scope is not None:
        stmt = stmt.where(scope)
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return int(await session.scalar(stmt) or 0)


async def _count_users_with_payment_for_links(
    session: AsyncSession,
    link_ids: list[int],
) -> int:
    stmt = (
        select(func.count(func.distinct(Payment.user_id)))
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .where(
            Payment.user_id.is_not(None),
            User.referral_link_id.in_(link_ids),
            user_counts_in_admin_stats(User),
        )
    )
    scope = _user_scope_filter()
    if scope is not None:
        stmt = stmt.where(scope)
    return int(await session.scalar(stmt) or 0)


async def _count_users_with_subscription_device_for_links(
    session: AsyncSession,
    link_ids: list[int],
) -> int:
    stmt = (
        select(func.count(func.distinct(SubscriptionDevice.user_id)))
        .select_from(SubscriptionDevice)
        .join(User, User.id == SubscriptionDevice.user_id)
        .where(
            User.referral_link_id.in_(link_ids),
            user_counts_in_admin_stats(User),
        )
    )
    scope = _user_scope_filter()
    if scope is not None:
        stmt = stmt.where(scope)
    return int(await session.scalar(stmt) or 0)


async def _active_users_count_for_utc_date_by_links(
    session: AsyncSession,
    cal_day: date,
    link_ids: list[int],
) -> int:
    pid = admin_project_id()
    user_project_sql = user_table_project_filter_sql("u", project_id=pid)
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
            {user_project_sql}
            AND u.referral_link_id = ANY(:link_ids)
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
        """
    )
    return int(
        (
            await session.execute(
                stmt,
                merge_project_sql_params(
                    {"cal_day": cal_day, "link_ids": link_ids},
                    project_id=pid,
                ),
            )
        ).scalar()
        or 0,
    )
