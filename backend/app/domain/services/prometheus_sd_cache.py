"""Кэш целей HTTP SD для Prometheus (Redis + опциональный refresh из scheduler)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.domain.services import prometheus_sd_service
from app.infrastructure.cache.json_redis_cache import redis_get_json, redis_set_json
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.prometheus_sd_cache")

_REDIS_KEY = "cache:prometheus_sd:node_exporter"


def prometheus_sd_cache_ttl_sec(cfg: Settings | None = None) -> int:
    cfg = cfg or settings
    return max(30, int(cfg.prometheus_sd_cache_ttl_seconds))


def read_node_exporter_targets_cache(cfg: Settings | None = None) -> list[dict[str, Any]] | None:
    data = redis_get_json(_REDIS_KEY)
    if not isinstance(data, list):
        return None
    return data


def write_node_exporter_targets_cache(
    targets: list[dict[str, Any]],
    *,
    cfg: Settings | None = None,
) -> None:
    redis_set_json(_REDIS_KEY, targets, ttl_sec=prometheus_sd_cache_ttl_sec(cfg))


def node_exporter_targets_sync(session: Session, cfg: Settings) -> list[dict[str, Any]]:
    port = int(cfg.provision_node_exporter_port)
    stmt = select(Server).where(Server.is_active.is_(True)).order_by(Server.id)
    servers = list(session.scalars(stmt).all())
    out: list[dict[str, Any]] = []
    for s in servers:
        inst = (s.prometheus_instance or "").strip()
        if not inst:
            inst = f"{s.host.strip()}:{port}"
        name = (s.name or "").strip()
        labels: dict[str, str] = {"server_id": str(s.id)}
        if name:
            labels["server_name"] = name
        out.append({"targets": [inst], "labels": labels})
    return out


def refresh_node_exporter_targets_cache_sync(cfg: Settings | None = None) -> int:
    """Пересчитать SD из БД и записать в Redis. Возвращает число targets."""
    cfg = cfg or settings
    from app.infrastructure.database.session import SessionLocal

    with SessionLocal() as session:
        targets = node_exporter_targets_sync(session, cfg)
    write_node_exporter_targets_cache(targets, cfg=cfg)
    return len(targets)


def invalidate_node_exporter_targets_cache() -> None:
    """Сбросить кэш SD; следующий запрос API/scheduler пересчитает из БД."""
    from app.infrastructure.cache import get_redis

    try:
        get_redis().delete(_REDIS_KEY)
    except Exception:
        log.exception("redis delete %s", _REDIS_KEY)


async def node_exporter_targets_cached(
    session: AsyncSession,
    cfg: Settings,
) -> list[dict[str, Any]]:
    cached = read_node_exporter_targets_cache(cfg)
    if cached is not None:
        return cached
    targets = await prometheus_sd_service.node_exporter_targets(session, cfg)
    write_node_exporter_targets_cache(targets, cfg=cfg)
    return targets
