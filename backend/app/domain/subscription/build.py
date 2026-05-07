"""Сборка тела подписки: список узлов, ``vless://`` URI, Base64, Clash Meta YAML."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote, urlencode

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BRAND_NAME
from app.domain.models.subscription import SubscriptionPayload
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.build")

# Дубликат первого узла по load_percent (после фильтрации каскада) с тем же endpoint.
SUBSCRIPTION_AUTO_RECOMMENDED_LABEL = "⚡ Auto (рекомендуемый)"


def subscription_servers_for_delivery(rows: list[Server]) -> list[Server]:
    """
    Узлы, которые попадают в тело подписки (JSON / Base64 / Clash).

    Если в выдаче есть пара каскада (РФ-вход с cascade_next_server_id), отдельная
    строка для внешнего exit не показывается — пользователь подключается только ко
    входу. Имя узла — как у одиночного сервера (без пометки «каскад»).
    Одиночные серверы и РФ-вход без привязанного exit не меняются.
    """
    referenced_exit_ids = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    if not referenced_exit_ids:
        return rows
    return [s for s in rows if s.id not in referenced_exit_ids]


async def subscription_servers_from_db(session: AsyncSession) -> list[Server]:
    """
    Узлы для выдачи в подписке: только чтение из БД (servers.load_percent обновляет фоновый планировщик).

    Дальше ``subscription_servers_for_delivery`` убирает внешние exit из пар
    «РФ-вход → exit», чтобы в клиенте не дублировать прямой доступ к exit.
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
    return list((await session.scalars(stmt)).all())


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
    Имя для подписки (vless #fragment и JSON name): одиночные узлы и РФ-вход с exit
    без отдельной пометки; РФ-вход без exit — «(RU, прямой)»; для exit из пары
    «(прямой)» — только если узел ещё попал в выдачу (обычно exit скрыт).
    """
    base = (s.name or s.country or s.host or "node").strip()
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
    fragment_override: str | None = None,
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
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
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
    name_override: str | None = None,
) -> dict[str, Any]:
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    uid = (client_uuid or "").strip()
    display_name = (
        name_override
        if name_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
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


def _first_subscription_eligible_server(
    rows: list[Server],
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
) -> Server | None:
    for s in rows:
        if (
            _vless_reality_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
            )
            is not None
        ):
            return s
    return None


def _unique_clash_proxy_name(base_label: str, seen: dict[str, int]) -> str:
    b = (base_label or "").strip() or "node"
    if b not in seen:
        seen[b] = 0
        return b
    seen[b] += 1
    return f"{b} ({seen[b]})"


def build_clash_subscription_yaml(user: User, rows: list[Server]) -> str:
    """Clash Meta: VLESS + REALITY; то же множество узлов, что и в Base64-подписке."""
    rows = subscription_servers_for_delivery(rows)
    client_uuid = (user.vless_uuid or "").strip()
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}
    auto_src = _first_subscription_eligible_server(
        rows,
        client_uuid=client_uuid,
        exit_ids_referenced=exit_ids_referenced,
    )
    if auto_src is not None:
        label_auto = SUBSCRIPTION_AUTO_RECOMMENDED_LABEL
        name = _unique_clash_proxy_name(label_auto, names_seen)
        pbk = (auto_src.reality_public_key or "").strip()
        sid = (auto_src.reality_short_id or "").strip()
        flow = (auto_src.vless_flow or "").strip() or "xtls-rprx-vision"
        fp = (auto_src.reality_fingerprint or "").strip() or "chrome"
        sni = _primary_sni(auto_src.reality_server_names, auto_src.reality_dest)
        host = (auto_src.host or "").strip()
        proxies.append(
            {
                "name": name,
                "type": "vless",
                "server": host,
                "port": int(auto_src.port),
                "uuid": client_uuid,
                "network": "tcp",
                "tls": True,
                "udp": True,
                "flow": flow,
                "servername": sni,
                "reality-opts": {
                    "public-key": pbk,
                    "short-id": sid,
                },
                "client-fingerprint": fp,
            }
        )
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
                    "short-id": sid,
                },
                "client-fingerprint": fp,
            }
        )
    group_name = BRAND_NAME
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
    rows = subscription_servers_for_delivery(rows)
    client_uuid = (user.vless_uuid or "").strip()
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []
    auto_src = _first_subscription_eligible_server(
        rows,
        client_uuid=client_uuid,
        exit_ids_referenced=exit_ids_referenced,
    )
    if auto_src is not None:
        servers_out.append(
            _server_to_subscription_dict(
                auto_src,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
                name_override=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
            )
        )
        auto_uri = _vless_reality_share_uri(
            auto_src,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            fragment_override=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        )
        if auto_uri:
            uris.append(auto_uri)
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
