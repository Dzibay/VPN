"""
JSON-профиль для Happ mobile: полный Xray-конфиг как у сторонних VPN.

Happ на iOS/Android не импортирует строки подписки с ``observatory`` + ``balancers``;
нужны ``dns``, ``log``, ``inbounds``, ``outbounds`` (tag ``proxy``), ``routing.rules``.
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.servers.reality_defaults import normalize_reality_spider_x
from app.domain.subscription.build import _primary_sni
from app.infrastructure.persistence.models.server import Server

_HAPP_MOBILE_SNIFFING: dict[str, Any] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
    "routeOnly": False,
}


def _happ_mobile_dns() -> dict[str, Any]:
    return {
        "queryStrategy": "UseIPv4",
        "servers": [
            "https://1.1.1.1/dns-query",
            "https://8.8.8.8/dns-query",
        ],
    }


def _happ_mobile_inbounds() -> list[dict[str, Any]]:
    return [
        {
            "tag": "socks",
            "port": 10808,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
            "sniffing": _HAPP_MOBILE_SNIFFING,
        },
        {
            "tag": "http",
            "port": 10809,
            "listen": "127.0.0.1",
            "protocol": "http",
            "settings": {"allowTransparent": False},
            "sniffing": _HAPP_MOBILE_SNIFFING,
        },
    ]


def _happ_mobile_log() -> dict[str, Any]:
    return {
        "loglevel": "Warning",
        "dnsLog": False,
    }


def _happ_mobile_routing() -> dict[str, Any]:
    """Минимальный routing как у рабочих подписок (без balancer)."""
    return {
        "domainMatcher": "hybrid",
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {
                "type": "field",
                "protocol": ["bittorrent"],
                "outboundTag": "direct",
            },
            {
                "type": "field",
                "ip": ["geoip:private"],
                "outboundTag": "direct",
            },
            {
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy",
            },
        ],
    }


def server_to_happ_mobile_proxy_outbound(
    s: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
    tag: str = "proxy",
) -> dict[str, Any] | None:
    """VLESS REALITY outbound в формате, который импортирует Happ mobile."""
    pbk = (s.reality_public_key or "").strip()
    if not pbk or "(" in pbk:
        return None
    sid = (s.reality_short_id or "").strip()
    if not sid:
        return None
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (client_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        return None
    host = (s.host or "").strip()
    uid = (client_uuid or "").strip()
    if not host or not uid:
        return None
    spx = normalize_reality_spider_x(s.reality_spider_x)
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": int(s.port),
                    "users": [
                        {
                            "id": uid,
                            "encryption": "none",
                            "flow": flow,
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "fingerprint": fp,
                "publicKey": pbk,
                "serverName": sni,
                "shortId": sid,
                "spiderX": spx,
            },
            "tcpSettings": {
                "header": {"type": "none"},
            },
        },
    }


def build_happ_mobile_profile_json(
    remark: str,
    server: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
    server_description: str | None = None,
) -> str | None:
    """
    Одна страна/узел = один полный JSON (отображается в Happ mobile как JSON).

    ``remarks`` — имя профиля в списке; ``meta.serverDescription`` — подпись в UI.
    """
    proxy = server_to_happ_mobile_proxy_outbound(
        server,
        client_uuid=client_uuid,
        client_fingerprint=client_fingerprint,
        tag="proxy",
    )
    if proxy is None:
        return None

    doc: dict[str, Any] = {
        "dns": _happ_mobile_dns(),
        "inbounds": _happ_mobile_inbounds(),
        "log": _happ_mobile_log(),
        "outbounds": [
            proxy,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "remarks": remark,
        "routing": _happ_mobile_routing(),
    }
    if server_description:
        doc["meta"] = {"serverDescription": server_description}

    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def build_happ_mobile_profile(
    remark: str,
    server: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
    server_description: str | None = None,
) -> dict[str, Any] | None:
    line = build_happ_mobile_profile_json(
        remark,
        server,
        client_uuid=client_uuid,
        client_fingerprint=client_fingerprint,
        server_description=server_description,
    )
    if line is None:
        return None
    return json.loads(line)
