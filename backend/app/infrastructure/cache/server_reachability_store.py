"""История TCP-доступности узлов (VPN-порт, опционально NE и exit) в Redis, без таблиц в БД."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

log = logging.getLogger("app.server_reachability_store")

KEY_PREFIX = "vpn:srv_reach:v1"


def reachability_redis_key(server_id: int) -> str:
    return f"{KEY_PREFIX}:{int(server_id)}"


def append_server_reachability_sample(
    r: Redis,
    server_id: int,
    sample: dict[str, Any],
    *,
    retention_seconds: int,
) -> None:
    """Добавить точку и обрезать всё старше окна retention."""
    ts = time.time()
    payload = dict(sample)
    payload["ts"] = ts
    member = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    key = reachability_redis_key(server_id)
    cutoff = ts - max(60, int(retention_seconds))
    pipe = r.pipeline()
    pipe.zadd(key, {member: ts})
    pipe.zremrangebyscore(key, "-inf", cutoff)
    pipe.expire(key, int(retention_seconds) + 7200)
    pipe.execute()


def _history_min_score(*, retention_seconds: int, hours: float | None) -> tuple[float, float]:
    """(now, min_score) для ZRANGEBYSCORE."""
    now = time.time()
    max_sec = float(retention_seconds)
    if hours is not None and hours > 0:
        window_sec = min(max_sec, float(hours) * 3600.0)
    else:
        window_sec = max_sec
    min_score = now - max(60.0, window_sec)
    return now, min_score


def decode_zrange_reachability_rows(raw_rows: list[Any] | None) -> list[dict[str, Any]]:
    """Разбор ответа Redis ZRANGEBYSCORE в отсортированный список снимков."""
    out: list[dict[str, Any]] = []
    if not raw_rows:
        return out
    for raw in raw_rows:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    out.sort(key=lambda d: float(d.get("ts") or 0.0))
    return out


def pipeline_fetch_reachability_histories(
    r: Redis,
    server_ids: list[int],
    *,
    retention_seconds: int,
    hours: float | None,
) -> dict[int, list[dict[str, Any]]]:
    """Пакетное чтение историй (один round-trip к Redis)."""
    if not server_ids:
        return {}
    _now, min_score = _history_min_score(retention_seconds=retention_seconds, hours=hours)
    pipe = r.pipeline()
    for sid in server_ids:
        pipe.zrangebyscore(reachability_redis_key(sid), min_score, "+inf")
    try:
        chunks = pipe.execute()
    except RedisError:
        log.exception("reachability pipeline: ошибка Redis")
        raise
    out: dict[int, list[dict[str, Any]]] = {}
    for sid, raw_rows in zip(server_ids, chunks):
        out[int(sid)] = decode_zrange_reachability_rows(raw_rows)
    return out


def fetch_server_reachability_history(
    r: Redis,
    server_id: int,
    *,
    retention_seconds: int,
    hours: float | None = None,
) -> list[dict[str, Any]]:
    """Сырые словари как в Redis (включая ts)."""
    key = reachability_redis_key(server_id)
    _now, min_score = _history_min_score(retention_seconds=retention_seconds, hours=hours)
    try:
        raw_rows = r.zrangebyscore(key, min_score, "+inf")
    except RedisError:
        log.exception("reachability history: Redis при чтении server_id=%s", server_id)
        raise
    return decode_zrange_reachability_rows(raw_rows)


def delete_server_reachability_key(r: Redis, server_id: int) -> None:
    """Лучше вызывать при удалении сервера из БД (опционально)."""
    try:
        r.delete(reachability_redis_key(server_id))
    except RedisError:
        log.warning("reachability: не удалось удалить ключ Redis для server_id=%s", server_id)
