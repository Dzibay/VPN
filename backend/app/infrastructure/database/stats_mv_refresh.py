"""Обновление кэша дневной пользовательской статистики (stats_users_daily_msk)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.infrastructure.database.session import SessionLocal

log = logging.getLogger(__name__)


def refresh_users_daily_stats_mv_sync() -> bool:
    """Пересчёт ``stats_users_daily_msk``. Возвращает False, если refresh уже идёт в другой сессии."""
    db = SessionLocal()
    try:
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
