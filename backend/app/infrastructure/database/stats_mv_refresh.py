"""Обновление кэша дневной пользовательской статистики (stats_users_daily_msk).

Multi-tenant: все функции обходят активные проекты и вызывают per-project SQL.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.infrastructure.database.session import SessionLocal

log = logging.getLogger(__name__)


def _list_active_project_ids(db) -> list[int]:
    rows = db.execute(text("SELECT id FROM projects WHERE is_active = TRUE ORDER BY id")).all()
    return [int(r[0]) for r in rows]


def flush_users_daily_stats_dirty_sync() -> int:
    """Пересчитать «грязные» холодные дни и upsert в stats_users_daily_msk (по всем проектам)."""
    db = SessionLocal()
    total = 0
    try:
        db.execute(text("SET statement_timeout = '600s'"))
        for pid in _list_active_project_ids(db):
            db.execute(
                text("SELECT fn_stats_users_daily_mark_cache_gaps_dirty(:pid)"),
                {"pid": pid},
            )
            n = int(
                db.execute(
                    text("SELECT fn_stats_users_daily_flush_dirty_project(:pid)"),
                    {"pid": pid},
                ).scalar()
                or 0
            )
            total += n
            if n > 0:
                log.info("stats_users_daily_msk[project=%s]: flush dirty, строк=%s", pid, n)
        db.commit()
        return total
    except Exception:
        db.rollback()
        log.exception("stats_users_daily_msk: ошибка flush dirty")
        raise
    finally:
        db.close()


def mark_users_daily_stats_recent_cold_dirty_sync(*, days: int = 90) -> None:
    """Пометить холодные дни для пересчёта (после батч-сбора трафика) — по всем активным проектам."""
    db = SessionLocal()
    try:
        db.execute(
            text("SELECT fn_stats_users_daily_mark_recent_cold_dirty(NULL, :days)"),
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
    """Полный пересчёт кэша по всем активным проектам. ``False``, если хотя бы один проект пропустил refresh (advisory lock занят)."""
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = '7200s'"))
        ok = bool(
            db.execute(
                text("SELECT fn_refresh_stats_users_daily_msk_all()"),
            ).scalar(),
        )
        db.commit()
        if ok:
            log.info("stats_users_daily_msk: refresh_all завершён")
        else:
            log.warning("stats_users_daily_msk: refresh_all — часть проектов не обработана")
        return ok
    except Exception:
        db.rollback()
        log.exception("stats_users_daily_msk: ошибка refresh_all")
        raise
    finally:
        db.close()
