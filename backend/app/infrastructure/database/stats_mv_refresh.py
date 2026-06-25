"""Обновление materialized view дневной пользовательской статистики."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.infrastructure.database.session import SessionLocal

log = logging.getLogger(__name__)


def refresh_users_daily_stats_mv_sync() -> None:
    """``REFRESH MATERIALIZED VIEW CONCURRENTLY mv_users_daily_stats`` (sync, для worker/scheduler)."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT fn_refresh_mv_users_daily_stats()"))
        db.commit()
        log.info("mv_users_daily_stats: refresh завершён")
    except Exception:
        db.rollback()
        log.exception("mv_users_daily_stats: ошибка refresh")
        raise
    finally:
        db.close()
