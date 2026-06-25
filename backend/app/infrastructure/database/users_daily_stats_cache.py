"""Очередь и статус пересчёта кэша stats_users_daily_msk."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.domain.models.users import (
    UsersDailyStatsCacheRefreshResponse,
    UsersDailyStatsCacheStatusResponse,
)
from app.infrastructure.cache import get_install_queue, get_redis
from app.infrastructure.database.stats_mv_refresh import refresh_users_daily_stats_mv_sync

log = logging.getLogger(__name__)

REFRESH_RUNNING_KEY = "vpn:stats:daily_msk:refresh_running"
LAST_REFRESH_KEY = "vpn:stats:daily_msk:last_refresh_at"
REFRESH_JOB_TIMEOUT_SECONDS = 7200


def _refresh_running() -> bool:
    try:
        return bool(get_redis().get(REFRESH_RUNNING_KEY))
    except RedisError:
        return False


def _last_refresh_at() -> datetime | None:
    try:
        raw = get_redis().get(LAST_REFRESH_KEY)
    except RedisError:
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        refresh_running=_refresh_running(),
        dirty_days_pending=int(row.dirty_days_pending or 0),
        hot_window_days=int(row.hot_window_days or 14),
        last_refresh_at=_last_refresh_at(),
    )


def enqueue_users_daily_stats_cache_refresh() -> UsersDailyStatsCacheRefreshResponse:
    if _refresh_running():
        return UsersDailyStatsCacheRefreshResponse(status="already_running")

    try:
        r = get_redis()
        if not r.set(REFRESH_RUNNING_KEY, "1", nx=True, ex=REFRESH_JOB_TIMEOUT_SECONDS):
            return UsersDailyStatsCacheRefreshResponse(status="already_running")
        q = get_install_queue()
        job = q.enqueue(
            "app.worker.jobs.refresh_users_daily_stats_cache_job",
            job_timeout=REFRESH_JOB_TIMEOUT_SECONDS,
        )
    except RedisError as e:
        log.exception("Redis/RQ недоступен (пересчёт stats_users_daily_msk)")
        try:
            get_redis().delete(REFRESH_RUNNING_KEY)
        except RedisError:
            pass
        raise ServiceUnavailableError(f"Очередь недоступна: {e}") from e
    except Exception:
        try:
            get_redis().delete(REFRESH_RUNNING_KEY)
        except RedisError:
            pass
        raise

    log.info("stats_users_daily_msk: в очереди пересчёт job_id=%s", job.id)
    return UsersDailyStatsCacheRefreshResponse(status="started", job_id=job.id)


def refresh_users_daily_stats_cache_job() -> dict[str, object]:
    """RQ-задача: полный пересчёт stats_users_daily_msk."""
    log.info("refresh_users_daily_stats_cache_job: старт")
    try:
        ran = refresh_users_daily_stats_mv_sync()
        if ran:
            try:
                get_redis().set(LAST_REFRESH_KEY, datetime.now(timezone.utc).isoformat())
            except RedisError:
                log.warning("stats_users_daily_msk: не удалось сохранить last_refresh_at в Redis")
        else:
            log.info("refresh_users_daily_stats_cache_job: пропуск (advisory lock занят)")
        return {"ran": ran}
    finally:
        try:
            get_redis().delete(REFRESH_RUNNING_KEY)
        except RedisError:
            log.warning("stats_users_daily_msk: не удалось снять refresh_running в Redis")
