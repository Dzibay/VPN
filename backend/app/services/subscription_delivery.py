"""Формирование ответа публичной подписки (/sub/...): узлы, vless://, Base64, YAML Clash."""

from __future__ import annotations

import base64
import logging
from typing import Any

import yaml
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.domain.subscription_open_apps import SUBSCRIPTION_IMPORT_DISPLAY_NAME
from app.models.server import Server
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.server_load_sync import sync_all_servers_load_from_prometheus

log = logging.getLogger("app.subscription_delivery")

_LOAD_SYNC_HOURS = 24


def _subscription_server_rows(session: Session) -> list[Server]:
    """
    Все валидные узлы для ссылки в подписке.

    Каскад (РФ → exit) не скрывает ни одну ногу: и вход (is_cascade_ru + cascade_next),
    и внешний id из пары, и полностью одиночный сервер (без участия в каскаде) попадают
    сюда по тем же критериям is_active, provision_ready, REALITY в БД. Пользователь
    в клиенте выбирает: прямой vless:// на зарубежный хост и/или на РФ-вход (трафик
    дальше пойдёт на exit по внутреннему каскаду на стороне Xray).
    """
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


def _node_subscription_label(
    s: Server,
    *,
    exit_ids_referenced: set[int],
) -> str:
    """
    Имя для подписки (vless #fragment и JSON name): одиночные узлы без пометок;
    RU-вход с каскадом / без; exit, на который ссылается каскад (прямое подключение).
    """
    base = (s.name or s.country or s.host or "node").strip()
    if s.is_cascade_ru_entry and s.cascade_next_server_id is not None:
        return f"{base} (каскад)"
    if s.is_cascade_ru_entry and s.cascade_next_server_id is None:
        return f"{base} (RU, прямой)"
    if s.id in exit_ids_referenced and not s.is_cascade_ru_entry:
        return f"{base} (прямой)"
    return base


def _vless_reality_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
) -> str | None:
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
    remark = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _server_to_subscription_dict(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
) -> dict[str, Any]:
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    uid = (client_uuid or "").strip()
    display_name = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    return {
        "id": s.id,
        "name": display_name,
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


def _unique_clash_proxy_name(base_label: str, seen: dict[str, int]) -> str:
    b = (base_label or "").strip() or "node"
    if b not in seen:
        seen[b] = 0
        return b
    seen[b] += 1
    return f"{b} ({seen[b]})"


def build_clash_subscription_yaml(user: User, rows: list[Server]) -> str:
    """Clash Meta: VLESS + REALITY; то же множество узлов, что и в Base64-подписке."""
    client_uuid = (user.vless_uuid or "").strip()
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}
    for s in rows:
        if (
            _vless_reality_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
            )
            is None
        ):
            continue
        label = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
        name = _unique_clash_proxy_name(label, names_seen)
        pbk = (s.reality_public_key or "").strip()
        sid = (s.reality_short_id or "").strip()
        flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
        fp = (s.reality_fingerprint or "").strip() or "chrome"
        sni = _primary_sni(s.reality_server_names, s.reality_dest)
        host = (s.host or "").strip()
        short_ids = ["", sid] if sid else [""]
        proxies.append(
            {
                "name": name,
                "type": "vless",
                "server": host,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "tcp",
                "tls": True,
                "udp": True,
                "flow": flow,
                "servername": sni,
                "reality-opts": {
                    "public-key": pbk,
                    "short-id": short_ids,
                },
                "client-fingerprint": fp,
            }
        )
    group_name = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    proxy_names = [p["name"] for p in proxies]
    if not proxy_names:
        doc: dict[str, Any] = {"proxies": [], "proxy-groups": [], "rules": []}
    else:
        doc = {
            "proxies": proxies,
            "proxy-groups": [
                {
                    "name": group_name,
                    "type": "select",
                    "proxies": proxy_names,
                }
            ],
            "rules": [f"MATCH,{group_name}"],
        }
    return yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def build_subscription_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    client_uuid = (user.vless_uuid or "").strip()
    # id узлов, на которые RU-входа с каскадом ссылаются как на exit
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []
    for s in rows:
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
            )
        )
        uri = _vless_reality_share_uri(
            s,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
        )
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
