"""Обновление кэша дневной пользовательской статистики (stats_users_daily_msk)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.infrastructure.database.session import SessionLocal

log = logging.getLogger(__name__)


def flush_users_daily_stats_dirty_sync() -> int:
    """Пересчитать «грязные» холодные дни и upsert в stats_users_daily_msk."""
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = '600s'"))
        db.execute(text("SELECT fn_stats_users_daily_mark_cache_gaps_dirty()"))
        n = int(db.execute(text("SELECT fn_stats_users_daily_flush_dirty()")).scalar() or 0)
        db.commit()
        if n > 0:
            log.info("stats_users_daily_msk: flush dirty, строк=%s", n)
        return n
    except Exception:
        db.rollback()
        log.exception("stats_users_daily_msk: ошибка flush dirty")
        raise
    finally:
        db.close()


def mark_users_daily_stats_recent_cold_dirty_sync(*, days: int = 90) -> None:
    """Пометить холодные дни для пересчёта (после батч-сбора трафика)."""
    db = SessionLocal()
    try:
        db.execute(
            text("SELECT fn_stats_users_daily_mark_recent_cold_dirty(:days)"),
            {"days": days},
        )
        db.commit()
    except Exception:
        db.rollback()
        log.exception("stats_users_daily_msk: ошибка mark_recent_cold_dirty")
        raise
    finally:
        db.close()


def refresh_users_daily_stats_mv_sync() -> bool:
    """Пересчёт ``stats_users_daily_msk``. Возвращает False, если refresh уже идёт в другой сессии."""
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = '7200s'"))
        ran = bool(
            db.execute(
                text("SELECT fn_refresh_stats_users_daily_msk()"),
            ).scalar(),
        )
        db.commit()
        if ran:
            log.info("stats_users_daily_msk: refresh завершён")
        return ran
    except Exception:
        db.rollback()
        log.exception("stats_users_daily_msk: ошибка refresh")
        raise
    finally:
        db.close()
