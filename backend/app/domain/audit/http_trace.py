"""Сохранение завершённого HTTP-запроса в БД (опционально, по настройкам)."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.core.request_subject import get_request_subject
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.persistence.models.user_http_request_trace import UserHttpRequestTrace

log = logging.getLogger("app.audit.http")

_UNKNOWN_AUDIT_LEVEL_LOGGED = False


def _normalized_route_path(path_with_query: str) -> str:
    """Путь без query и без завершающего слэша (кроме корня "")."""
    p = (path_with_query or "").split("?", 1)[0].strip()
    if not p:
        return "/"
    return p.rstrip("/") or "/"


def http_audit_skip_persist_for_path(path_with_query: str, *, api_prefix: str) -> bool:
    """Не писать в БД высокочастотные служебные эндпоинты (пробы, SD Prometheus)."""
    normalized = _normalized_route_path(path_with_query)
    pfx = (api_prefix or "/api").strip()
    if not pfx.startswith("/"):
        pfx = "/" + pfx.lstrip("/")
    pfx = pfx.rstrip("/")
    health = f"{pfx}/health"
    if normalized == health:
        return True
    prom_root = f"{pfx}/prometheus"
    if normalized == prom_root or normalized.startswith(prom_root + "/"):
        return True
    return False


def http_audit_should_persist_row(*, resolved_user_id: int | None, level_raw: str) -> bool:
    """
    OFF — не писать; INFO (и WARNING/ERROR/CRITICAL) — только при известном user_id;
    DEBUG — любые запросы.
    """
    global _UNKNOWN_AUDIT_LEVEL_LOGGED

    lvl = (level_raw or "").strip().upper()
    if lvl in ("", "OFF", "NONE", "DISABLED", "NOTSET", "0", "FALSE"):
        return False
    if lvl == "DEBUG":
        return True
    if lvl in ("INFO", "WARNING", "ERROR", "CRITICAL"):
        return resolved_user_id is not None
    if not _UNKNOWN_AUDIT_LEVEL_LOGGED:
        _UNKNOWN_AUDIT_LEVEL_LOGGED = True
        log.warning(
            "Неизвестный HTTP_AUDIT_DB_LOG_LEVEL=%r — записи аудита отключены; допустимо: OFF, INFO, DEBUG",
            level_raw,
        )
    return False


async def persist_http_request_trace_if_configured(
    *,
    request_id: str,
    scope_path_with_query: str,
    http_method: str,
    status_code: int,
    duration_ms: float,
) -> None:
    cfg = get_settings()

    if http_audit_skip_persist_for_path(
        scope_path_with_query,
        api_prefix=cfg.api_prefix,
    ):
        return

    user_id, subject_source = get_request_subject()

    if not http_audit_should_persist_row(
        resolved_user_id=user_id,
        level_raw=cfg.http_audit_db_log_level,
    ):
        return

    row = UserHttpRequestTrace(
        request_id=request_id,
        user_id=user_id,
        subject_source=subject_source,
        http_method=http_method,
        path=scope_path_with_query,
        status_code=status_code,
        duration_ms=duration_ms,
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception:
        log.exception(
            "Не удалось записать user_http_request_traces (request_id=%s path=%s)",
            request_id,
            scope_path_with_query,
        )
