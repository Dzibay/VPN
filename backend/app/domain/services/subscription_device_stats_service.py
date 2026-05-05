"""Агрегаты по subscription_devices и трафику (user_server_traffic) для админки."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


async def admin_stats_subscription_devices_by_user_agent(
    session: AsyncSession,
) -> list[dict[str, int | str]]:
    """
    По каждому непустому user_agent: число пользователей с таким устройством и число из них
    с суммарным VPN-трафиком (up_bytes + down_bytes) > 0 по всем строкам user_server_traffic.
    """
    traffic_users = (
        select(UserServerTraffic.user_id.label("uid"))
        .group_by(UserServerTraffic.user_id)
        .having(func.sum(UserServerTraffic.up_bytes + UserServerTraffic.down_bytes) > 0)
        .subquery()
    )

    traffic_match = SubscriptionDevice.user_id.in_(select(traffic_users.c.uid))
    users_with_traffic_expr = func.count(
        func.distinct(case((traffic_match, SubscriptionDevice.user_id), else_=None)),
    )

    stmt = (
        select(
            SubscriptionDevice.user_agent,
            func.count(func.distinct(SubscriptionDevice.user_id)).label("connected_users"),
            users_with_traffic_expr.label("users_with_traffic"),
        )
        .where(SubscriptionDevice.user_agent.is_not(None))
        .where(func.trim(SubscriptionDevice.user_agent) != "")
        .group_by(SubscriptionDevice.user_agent)
        .order_by(func.count(func.distinct(SubscriptionDevice.user_id)).desc())
    )

    rows = (await session.execute(stmt)).all()
    return [
        {
            "user_agent": str(ua),
            "connected_users": int(n_users or 0),
            "users_with_traffic": int(n_traffic or 0),
        }
        for ua, n_users, n_traffic in rows
    ]
