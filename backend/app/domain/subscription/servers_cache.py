"""In-process кэш списка узлов для выдачи подписки (снижает нагрузку при всплесках GET /sub/)."""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.subscription.servers_cache")

_CACHE_TTL_SEC = 30.0
_cached_at: float = 0.0
_cached_rows: list[Server] = []
_lock = asyncio.Lock()


async def subscription_delivery_servers_cached(
    session: AsyncSession,
    *,
    loader,
) -> list[Server]:
    """
    ``loader`` — async callable(session) -> list[Server], обычно ``subscription_servers_from_db``.
    Объекты Server отсоединяются от сессии перед кэшированием.
    """
    global _cached_at, _cached_rows

    now = time.monotonic()
    if _cached_rows and (now - _cached_at) < _CACHE_TTL_SEC:
        return _cached_rows

    async with _lock:
        now = time.monotonic()
        if _cached_rows and (now - _cached_at) < _CACHE_TTL_SEC:
            return _cached_rows
        try:
            rows = await loader(session)
            for row in rows:
                try:
                    session.expunge(row)
                except Exception:
                    pass
            _cached_rows = rows
            _cached_at = time.monotonic()
        except Exception:
            log.exception("subscription servers cache: reload failed")
            if _cached_rows:
                return _cached_rows
            raise
        return _cached_rows


def invalidate_subscription_delivery_servers_cache() -> None:
    global _cached_at
    _cached_at = 0.0
