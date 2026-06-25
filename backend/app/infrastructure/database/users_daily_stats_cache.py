"""Статус умного кэша stats_users_daily_msk (обновление — триггеры + фоновый flush)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.users import UsersDailyStatsCacheStatusResponse


async def users_daily_stats_cache_status(
    session: AsyncSession,
) -> UsersDailyStatsCacheStatusResponse:
    row = (
        await session.execute(
            text(
                """
                SELECT
                    fn_stats_users_daily_msk_is_ready() AS cache_ready,
                    COUNT(*)::int AS row_count,
                    MIN(stats_date) AS date_from,
                    MAX(stats_date) AS date_to,
                    fn_stats_users_daily_dirty_count()::int AS dirty_days_pending,
                    fn_stats_users_daily_hot_days()::int AS hot_window_days
                FROM stats_users_daily_msk
                """,
            ),
        )
    ).one()
    return UsersDailyStatsCacheStatusResponse(
        cache_ready=bool(row.cache_ready),
        row_count=int(row.row_count or 0),
        date_from=row.date_from,
        date_to=row.date_to,
        dirty_days_pending=int(row.dirty_days_pending or 0),
        hot_window_days=int(row.hot_window_days or 14),
    )
