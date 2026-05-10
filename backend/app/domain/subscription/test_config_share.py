"""Тестовые конфигурации из JSON → формат подписки (vless://, Base64, Clash YAML).

Берётся один «прокси»-outbound из каждого конфига: сначала tag ``proxy``, иначе первый
не-служебный outbound. Поддерживается VLESS+REALITY поверх TCP (как в типичном клиентском экспорте).
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote, urlencode

import yaml

from app.constants import BRAND_NAME
from app.domain.models.subscription import SubscriptionPayload
from app.domain.models.test_configurations import TestConfigurationItem
from app.domain.servers.reality_defaults import normalize_reality_spider_x

log = logging.getLogger(__name__)

_SKIP_PROTOCOLS = frozenset({"freedom", "blackhole", "dns", "loopback"})


def _unique_proxy_list_name(base_label: str, seen: dict[str, int]) -> str:
    b = (base_label or "").strip() or "node"
    if b not in seen:
        seen[b] = 0
        return b
    seen[b] += 1
    return f"{b} ({seen[b]})"


def display_label_for_test_item(item: TestConfigurationItem) -> str:
    if item.title and str(item.title).strip():
        return str(item.title).strip()
    r = item.config.get("remarks")
    if isinstance(r, str) and r.strip():
        return r.strip()
    return item.id


def pick_proxy_outbound(config: dict[str, Any]) -> dict[str, Any] | None:
    raw = config.get("outbounds")
    if not isinstance(raw, list):
        return None
    for ob in raw:
        if isinstance(ob, dict) and ob.get("tag") == "proxy":
            return ob
    for ob in raw:
        if not isinstance(ob, dict):
            continue
        p = (ob.get("protocol") or "").strip().lower()
        if not p or p in _SKIP_PROTOCOLS:
            continue
        return ob
    return None


def outbound_vless_reality_tcp_to_uri(outbound: dict[str, Any], *, fragment: str) -> str | None:
    if (outbound.get("protocol") or "").strip().lower() != "vless":
        return None
    settings = outbound.get("settings") if isinstance(outbound.get("settings"), dict) else {}
    vnext = settings.get("vnext")
    if not isinstance(vnext, list) or not vnext or not isinstance(vnext[0], dict):
        return None
    server = vnext[0]
    address = (server.get("address") or "").strip()
    port = int(server.get("port") or 0)
    users = server.get("users")
    if not isinstance(users, list) or not users or not isinstance(users[0], dict):
        return None
    user = users[0]
    uuid = (user.get("id") or "").strip()
    encryption = (user.get("encryption") or "none").strip() or "none"
    flow = (user.get("flow") or "").strip() or "xtls-rprx-vision"

    ss = outbound.get("streamSettings") if isinstance(outbound.get("streamSettings"), dict) else {}
    network = (ss.get("network") or "tcp").strip().lower()
    security = (ss.get("security") or "").strip().lower()
    if security != "reality" or network != "tcp":
        log.debug(
            "test config outbound: only vless+reality+tcp supported, got security=%s network=%s",
            security,
            network,
        )
        return None

    rs = ss.get("realitySettings") if isinstance(ss.get("realitySettings"), dict) else {}
    fp = (rs.get("fingerprint") or "chrome").strip() or "chrome"
    sni = (rs.get("serverName") or "").strip()
    pbk = (rs.get("publicKey") or "").strip()
    sid = (rs.get("shortId") or "").strip()
    spx = normalize_reality_spider_x(rs.get("spiderX"))

    if not address or not port or not uuid or not sni or not pbk:
        return None

    params: dict[str, str] = {
        "encryption": encryption,
        "security": "reality",
        "type": "tcp",
        "headerType": "none",
        "flow": flow,
        "sni": sni,
        "fp": fp,
        "pbk": pbk,
        "spx": spx,
    }
    if sid:
        params["sid"] = sid
    query = urlencode(params, quote_via=quote, safe="")
    fragment_q = quote(fragment, safe="")
    return f"vless://{uuid}@{address}:{port}?{query}#{fragment_q}"


def outbound_vless_reality_tcp_to_clash_proxy(
    outbound: dict[str, Any],
    *,
    name: str,
) -> dict[str, Any] | None:
    if (outbound.get("protocol") or "").strip().lower() != "vless":
        return None
    settings = outbound.get("settings") if isinstance(outbound.get("settings"), dict) else {}
    vnext = settings.get("vnext")
    if not isinstance(vnext, list) or not vnext or not isinstance(vnext[0], dict):
        return None
    server = vnext[0]
    host = (server.get("address") or "").strip()
    port = int(server.get("port") or 0)
    users = server.get("users")
    if not isinstance(users, list) or not users or not isinstance(users[0], dict):
        return None
    user = users[0]
    uuid = (user.get("id") or "").strip()
    flow = (user.get("flow") or "").strip() or "xtls-rprx-vision"

    ss = outbound.get("streamSettings") if isinstance(outbound.get("streamSettings"), dict) else {}
    network = (ss.get("network") or "tcp").strip().lower()
    security = (ss.get("security") or "").strip().lower()
    if security != "reality" or network != "tcp":
        return None

    rs = ss.get("realitySettings") if isinstance(ss.get("realitySettings"), dict) else {}
    fp = (rs.get("fingerprint") or "chrome").strip() or "chrome"
    sni = (rs.get("serverName") or "").strip()
    pbk = (rs.get("publicKey") or "").strip()
    sid = (rs.get("shortId") or "").strip()
    spx = normalize_reality_spider_x(rs.get("spiderX"))

    if not host or not port or not uuid or not sni or not pbk:
        return None

    reality_opts: dict[str, Any] = {
        "public-key": pbk,
        "spider-x": spx,
    }
    if sid:
        reality_opts["short-id"] = sid

    return {
        "name": name,
        "type": "vless",
        "server": host,
        "port": port,
        "uuid": uuid,
        "network": "tcp",
        "tls": True,
        "udp": True,
        "flow": flow,
        "servername": sni,
        "reality-opts": reality_opts,
        "client-fingerprint": fp,
        "tfo": True,
    }


def build_test_subscription_payload(items: list[TestConfigurationItem]) -> SubscriptionPayload:
    """Один vless:// на запись (если outbound распознан)."""
    uris: list[str] = []
    servers_out: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}

    for item in items:
        label = display_label_for_test_item(item)
        ob = pick_proxy_outbound(item.config)
        if ob is None:
            log.warning("test configuration id=%s: no proxy outbound found", item.id)
            continue
        name = _unique_proxy_list_name(label, names_seen)
        uri = outbound_vless_reality_tcp_to_uri(ob, fragment=name)
        if not uri:
            log.warning(
                "test configuration id=%s: expected vless+reality+tcp outbound",
                item.id,
            )
            continue
        uris.append(uri)
        servers_out.append(
            {
                "id": item.id,
                "name": name,
                "protocol": "vless",
                "subscription_note": "test_configuration_file",
            }
        )

    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=None,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )


def build_test_configs_clash_yaml(items: list[TestConfigurationItem]) -> str:
    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}

    for item in items:
        label = display_label_for_test_item(item)
        ob = pick_proxy_outbound(item.config)
        if ob is None:
            continue
        name = _unique_proxy_list_name(label, names_seen)
        clash = outbound_vless_reality_tcp_to_clash_proxy(ob, name=name)
        if clash:
            proxies.append(clash)

    group_name = f"{BRAND_NAME} (test)"
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
