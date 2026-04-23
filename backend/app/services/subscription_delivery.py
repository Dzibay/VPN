"""Формирование ответа публичной подписки (/sub/...): узлы, vless://, Base64."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.server import Server
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.server_load_sync import sync_all_servers_load_from_prometheus

log = logging.getLogger("app.subscription_delivery")

_LOAD_SYNC_HOURS = 24


def _subscription_server_rows(session: Session) -> list[Server]:
    stmt = (
        select(Server)
        .where(
            Server.is_active.is_(True),
            Server.provision_ready.is_(True),
            Server.reality_public_key.isnot(None),
            Server.reality_public_key != "",
        )
        .order_by(Server.load_percent.asc(), Server.id.asc())
    )
    return list(session.scalars(stmt).all())


def subscription_servers_after_prometheus_sync() -> list[Server]:
    db = SessionLocal()
    try:
        sync_all_servers_load_from_prometheus(db, hours=_LOAD_SYNC_HOURS)
        return _subscription_server_rows(db)
    finally:
        db.close()


def _primary_sni(server_names: str, dest: str) -> str:
    for part in (server_names or "").split(","):
        host = part.strip().split(":", 1)[0].strip()
        if host:
            return host
    d = (dest or "").strip()
    if not d:
        return ""
    return d.rsplit(":", 1)[0] if ":" in d else d


def _vless_reality_share_uri(s: Server, *, client_uuid: str) -> str | None:
    pbk = (s.reality_public_key or "").strip()
    if not pbk or "(" in pbk:
        log.warning(
            "Пропуск узла id=%s в подписке: некорректный reality_public_key",
            s.id,
        )
        return None
    sid = (s.reality_short_id or "").strip()
    if not sid:
        log.warning("Пропуск узла id=%s: пустой reality_short_id", s.id)
        return None
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (s.reality_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести SNI", s.id)
        return None

    params = {
        "encryption": "none",
        "security": "reality",
        "type": "tcp",
        "headerType": "none",
        "flow": flow,
        "sni": sni,
        "fp": fp,
        "pbk": pbk,
        "sid": sid,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (s.name or s.country or s.host or "node").strip()
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _server_to_subscription_dict(s: Server, *, client_uuid: str) -> dict[str, Any]:
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    uid = (client_uuid or "").strip()
    return {
        "id": s.id,
        "name": s.name or s.host,
        "country": s.country,
        "address": s.host,
        "port": s.port,
        "uuid": uid,
        "flow": s.vless_flow,
        "encryption": "none",
        "network": "tcp",
        "security": "reality",
        "sni": sni,
        "fingerprint": s.reality_fingerprint,
        "public_key": s.reality_public_key,
        "short_id": s.reality_short_id,
        "dest": s.reality_dest,
        "server_names": s.reality_server_names,
    }


def build_subscription_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    client_uuid = (user.vless_uuid or "").strip()
    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []
    for s in rows:
        servers_out.append(_server_to_subscription_dict(s, client_uuid=client_uuid))
        uri = _vless_reality_share_uri(s, client_uuid=client_uuid)
        if uri:
            uris.append(uri)
    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )
