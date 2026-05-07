"""
Периодический TCP-опрос узлов (порт Xray / каскадный exit / node_exporter) и запись истории в Redis.

Проверка «принимает трафик» на практике — успешное TCP-соединение с хоста планировщика к host:port
VPN inbound (как ручной GET /servers/{id}/ping). Полноценный VLESS handshake здесь не выполняется.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.domain.services.servers_service import tcp_probes_payload
from app.infrastructure.cache import get_redis
from app.infrastructure.cache.server_reachability_store import append_server_reachability_sample
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.server_reachability_scheduler")


def _sample_from_tcp(tcp: dict) -> dict:
    v_ok, v_ms, v_err = tcp.get("vpn", (False, None, ""))
    sample: dict = {
        "vpn_ok": bool(v_ok),
        "vpn_ms": v_ms,
        "vpn_err": (str(v_err).strip() or "")[:300],
    }
    if "ne" in tcp:
        n_ok, n_ms, n_err = tcp["ne"]
        sample["ne_ok"] = bool(n_ok)
        sample["ne_ms"] = n_ms
        sample["ne_err"] = (str(n_err).strip() or "")[:200]
    if "exit" in tcp:
        e_ok, e_ms, e_err = tcp["exit"]
        sample["exit_ok"] = bool(e_ok)
        sample["exit_ms"] = e_ms
        sample["exit_err"] = (str(e_err).strip() or "")[:200]
    return sample


def _probe_server_tcp(db: Session, server: Server, timeout_sec: float) -> tuple[int, dict]:
    host = (server.host or "").strip()
    sid = int(server.id)
    if not host:
        return sid, {"vpn_ok": False, "vpn_ms": None, "vpn_err": "empty host"}

    ex_host: str | None = None
    ex_port: int | None = None
    if server.is_cascade_ru_entry and server.cascade_next_server_id is not None:
        ex = db.get(Server, int(server.cascade_next_server_id))
        if ex is not None:
            ex_host = (ex.host or "").strip() or None
            ex_port = int(ex.port)

    tcp = tcp_probes_payload(
        host=host,
        port=int(server.port),
        exit_host=ex_host,
        exit_port=ex_port,
        timeout_sec=timeout_sec,
        cfg=settings,
    )
    return sid, _sample_from_tcp(tcp)


def _probe_by_server_id(server_id: int, timeout_sec: float) -> tuple[int, dict]:
    """Отдельная sync-сессия на вызов — безопасно для ThreadPoolExecutor."""
    with SessionLocal() as sess:
        srv = sess.get(Server, server_id)
        if srv is None:
            return server_id, {
                "vpn_ok": False,
                "vpn_ms": None,
                "vpn_err": "server row missing",
            }
        return _probe_server_tcp(sess, srv, timeout_sec)


def run_scheduled_server_reachability_probe() -> None:
    timeout_sec = max(0.5, float(settings.server_reachability_tcp_timeout_seconds))
    retention = max(3600, int(settings.server_reachability_history_retention_seconds))
    parallelism = max(1, min(32, int(settings.server_reachability_parallelism)))

    db = SessionLocal()
    try:
        stmt = select(Server).where(
            Server.is_active.is_(True),
            Server.provision_ready.is_(True),
        )
        server_ids = [int(s.id) for s in db.scalars(stmt).all()]
    finally:
        db.close()

    if not server_ids:
        log.debug("reachability probe: нет активных provision_ready узлов")
        return

    results: list[tuple[int, dict]]

    if parallelism <= 1 or len(server_ids) == 1:
        results = [_probe_by_server_id(sid, timeout_sec) for sid in server_ids]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=parallelism) as ex:
            futs = [ex.submit(_probe_by_server_id, sid, timeout_sec) for sid in server_ids]
            for fut in as_completed(futs):
                results.append(fut.result())

    ok_vpn = sum(1 for _sid, sm in results if sm.get("vpn_ok"))
    try:
        r = get_redis()
        for sid, sample in results:
            append_server_reachability_sample(
                r,
                sid,
                sample,
                retention_seconds=retention,
            )
        log.info(
            "reachability probe: узлов=%s vpn_tcp_ok=%s (timeout=%ss, retention=%ss)",
            len(results),
            ok_vpn,
            timeout_sec,
            retention,
        )
    except RedisError:
        log.exception("reachability probe: не удалось записать историю в Redis")


async def periodic_server_reachability_loop() -> None:
    interval = max(30, int(settings.server_reachability_interval_seconds))
    initial = max(0, int(settings.server_reachability_initial_delay_seconds))
    log.info(
        "server reachability scheduler: запущен (интервал=%ss, задержка=%ss)",
        interval,
        initial,
    )
    try:
        await asyncio.sleep(initial)
        while True:
            await run_in_threadpool(run_scheduled_server_reachability_probe)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("server reachability scheduler: остановлен")
        raise
