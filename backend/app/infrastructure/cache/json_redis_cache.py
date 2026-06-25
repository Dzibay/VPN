"""Простой JSON-кэш в Redis (sync-клиент RQ)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.infrastructure.cache import get_redis

log = logging.getLogger("app.cache.redis_json")

RedisError = Exception  # redis.exceptions.RedisError при импорте; ловим широко ниже


def redis_get_json(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
    except Exception:
        log.exception("redis get %s", key)
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("redis get %s: invalid JSON", key)
        return None


def redis_set_json(key: str, value: Any, *, ttl_sec: int) -> None:
    if ttl_sec <= 0:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        get_redis().setex(key, int(ttl_sec), payload)
    except Exception:
        log.exception("redis setex %s", key)
