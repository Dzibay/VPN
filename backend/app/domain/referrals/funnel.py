"""Воронка реферальной ссылки: клики → регистрации → пользователи с трафиком/устройствами/активные.

Используется в админ-эндпоинте сводки по выбранной ссылке (или по всему сайту, если
``referral_link_id is None``). Все сводные числа неотрицательны: невалидные значения из
агрегатов SQL приводятся к 0.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.time import utc_today
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.domain.users.daily_stats import (
    active_users_count_for_utc_date,
    count_users_with_subscription_device,
)
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


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
    _cfg: object,
):
    """Сводка воронки по выбранной ссылке (``referral_link_id``) или по всем пользователям сайта."""
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

    if referral_link_id is not None:
        row = (
            await session.scalars(
                select(ReferralLink).where(ReferralLink.id == referral_link_id).limit(1),
            )
        ).first()
        if row is None:
            raise NotFoundError("Реферальная ссылка не найдена")
        registrations_total_raw = row.registrations_count
        users_with_traffic_raw = await session.scalar(
            select(func.count())
            .select_from(per_user_traffic)
            .join(User, User.id == per_user_traffic.c.uid)
            .where(User.referral_link_id == referral_link_id),
        )
        today = utc_today()
        with_dev = await count_users_with_subscription_device(session, referral_link_id)
        active_today = await active_users_count_for_utc_date(session, today, referral_link_id)
        return ReferralFunnelSummary(
            clicks_total=_nz_metric(row.clicks_count),
            registrations_total=_nz_metric(registrations_total_raw),
            users_with_traffic=_nz_metric(users_with_traffic_raw),
            users_with_subscription_device=_nz_metric(with_dev),
            active_users_today_utc=_nz_metric(active_today),
        )

    registrations_total_raw = await session.scalar(select(func.count()).select_from(User))
    users_with_traffic_raw = await session.scalar(
        select(func.count()).select_from(per_user_traffic),
    )
    today = utc_today()
    with_dev = await count_users_with_subscription_device(session, None)
    active_today = await active_users_count_for_utc_date(session, today, None)

    return ReferralFunnelSummary(
        clicks_total=None,
        registrations_total=_nz_metric(registrations_total_raw),
        users_with_traffic=_nz_metric(users_with_traffic_raw),
        users_with_subscription_device=_nz_metric(with_dev),
        active_users_today_utc=_nz_metric(active_today),
    )
