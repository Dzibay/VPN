"""In-memory кэш заблокированных IP (обновляется из БД, TTL для multi-worker)."""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import text

from app.infrastructure.database.session import async_engine

log = logging.getLogger("app.security.blocked_ip")

_blocked: frozenset[str] = frozenset()
_last_load_monotonic: float = 0.0
_TTL_SEC = 15.0
_lock = asyncio.Lock()


async def ensure_blocked_ips_loaded(*, force: bool = False) -> frozenset[str]:
    global _blocked, _last_load_monotonic

    now = time.monotonic()
    if not force and _blocked and (now - _last_load_monotonic) < _TTL_SEC:
        return _blocked

    async with _lock:
        now = time.monotonic()
        if not force and _blocked and (now - _last_load_monotonic) < _TTL_SEC:
            return _blocked
        try:
            async with async_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT ip FROM blocked_ips ORDER BY id ASC"),
                )
                rows = [str(r[0]) for r in result.all()]
            _blocked = frozenset(rows)
            _last_load_monotonic = time.monotonic()
        except Exception:
            log.exception("Не удалось загрузить blocked_ips")
        return _blocked


def invalidate_blocked_ips_cache() -> None:
    global _last_load_monotonic
    _last_load_monotonic = 0.0


def is_ip_blocked(client_ip: str | None, blocked: frozenset[str]) -> bool:
    return bool(client_ip and client_ip in blocked)
