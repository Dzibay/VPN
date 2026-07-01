"""Агрегаты по subscription_devices и трафику (user_server_traffic) для админки."""

from __future__ import annotations

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.admin_project_scope import project_scope_clause
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


async def admin_stats_subscription_devices_by_user_agent(
    session: AsyncSession,
) -> list[dict[str, int | str]]:
    """
    По каждой паре (префикс User-Agent до первого «/», ОС из x-device-os): число пользователей
    с таким устройством и число из них с суммарным VPN-трафиком (up_bytes + down_bytes) > 0
    по всем строкам user_server_traffic.
    """
    scope = project_scope_clause(SubscriptionDevice)
    traffic_scope = project_scope_clause(UserServerTraffic)
    traffic_users_q = (
        select(UserServerTraffic.user_id.label("uid"))
        .group_by(UserServerTraffic.user_id)
        .having(func.sum(UserServerTraffic.up_bytes + UserServerTraffic.down_bytes) > 0)
    )
    if traffic_scope is not None:
        traffic_users_q = traffic_users_q.where(traffic_scope)
    traffic_users = traffic_users_q.subquery()
    heavy_traffic_users_q = (
        select(UserServerTraffic.user_id.label("uid"))
        .group_by(UserServerTraffic.user_id)
        .having(func.sum(UserServerTraffic.up_bytes + UserServerTraffic.down_bytes) > 100 * 1024 * 1024)
    )
    if traffic_scope is not None:
        heavy_traffic_users_q = heavy_traffic_users_q.where(traffic_scope)
    heavy_traffic_users = heavy_traffic_users_q.subquery()
    traffic_users_today_q = (
        select(UserServerTraffic.user_id.label("uid"))
        .where(UserServerTraffic.traffic_date == func.current_date())
        .group_by(UserServerTraffic.user_id)
        .having(func.sum(UserServerTraffic.up_bytes + UserServerTraffic.down_bytes) > 0)
    )
    if traffic_scope is not None:
        traffic_users_today_q = traffic_users_today_q.where(traffic_scope)
    traffic_users_today = traffic_users_today_q.subquery()

    traffic_match = SubscriptionDevice.user_id.in_(select(traffic_users.c.uid))
    heavy_traffic_match = SubscriptionDevice.user_id.in_(select(heavy_traffic_users.c.uid))
    traffic_today_match = SubscriptionDevice.user_id.in_(select(traffic_users_today.c.uid))
    users_with_traffic_expr = func.count(
        func.distinct(case((traffic_match, SubscriptionDevice.user_id), else_=None)),
    )
    users_over_100mb_expr = func.count(
        func.distinct(case((heavy_traffic_match, SubscriptionDevice.user_id), else_=None)),
    )
    active_users_today_expr = func.count(
        func.distinct(case((traffic_today_match, SubscriptionDevice.user_id), else_=None)),
    )

    ua_prefix = func.split_part(func.trim(SubscriptionDevice.user_agent), "/", 1)
    os_bucket = func.coalesce(
        func.nullif(func.trim(SubscriptionDevice.os), literal("")),
        literal(""),
    )

    stmt = (
        select(
            ua_prefix.label("user_agent"),
            os_bucket.label("os"),
            func.count(func.distinct(SubscriptionDevice.user_id)).label("connected_users"),
            users_with_traffic_expr.label("users_with_traffic"),
            users_over_100mb_expr.label("users_over_100mb"),
            active_users_today_expr.label("active_users_today"),
        )
        .where(SubscriptionDevice.user_agent.is_not(None))
        .where(func.trim(SubscriptionDevice.user_agent) != "")
        .where(ua_prefix != "")
    )
    if scope is not None:
        stmt = stmt.where(scope)
    stmt = (
        stmt
        .group_by(ua_prefix, os_bucket)
        .order_by(func.count(func.distinct(SubscriptionDevice.user_id)).desc())
    )

    rows = (await session.execute(stmt)).all()
    return [
        {
            "user_agent": str(ua),
            "os": str(os_val or ""),
            "connected_users": int(n_users or 0),
            "users_with_traffic": int(n_traffic or 0),
            "users_over_100mb": int(n_over_100mb or 0),
            "active_users_today": int(n_active_today or 0),
        }
        for ua, os_val, n_users, n_traffic, n_over_100mb, n_active_today in rows
    ]
