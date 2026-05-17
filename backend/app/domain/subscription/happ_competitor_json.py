"""
JSON-профиль Happ в стиле конкурентов: один конфиг, несколько outbounds,
``routing.balancers`` (``leastLoad``), ``observatory``, ``fallbackTag``.

Полные ``dns`` / ``policy`` / ``inbounds``, трафик через balancer по правилам routing.
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.servers.reality_defaults import normalize_reality_spider_x
from app.domain.subscription.build import (
    _XRAY_VLESS_STREAM_SETTINGS_SOCKOPT,
    _primary_sni,
)
from app.infrastructure.persistence.models.server import Server

_COMPETITOR_BALANCER_TAG = "auto-balance"
_COMPETITOR_PROBE_URL = "http://1.1.1.1/generate_204"
_COMPETITOR_PROBE_INTERVAL = "10s"
_COMPETITOR_DNS_TAG = "dns-out"
_DIRECT_SERVICE_PORTS = (
    "22,25,135-139,465,587,593,2525,3306,3389,5432,6379,11211,1900"
)
_COMPETITOR_SNIFFING: dict[str, Any] = {
    "enabled": True,
    "routeOnly": False,
    "destOverride": ["http", "tls", "quic"],
}


def competitor_outbound_tag(server_id: int, *, whitelist: bool) -> str:
    prefix = "wl" if whitelist else "rec"
    return f"{prefix}-{int(server_id)}"


def server_to_competitor_vless_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    """VLESS REALITY outbound без полей, которые отсекают Happ mobile."""
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
    stream_settings: dict[str, Any] = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "fingerprint": fp,
            "serverName": sni,
            "publicKey": pbk,
            "shortId": sid,
            "spiderX": spx,
        },
        "tcpSettings": {"header": {"type": "none"}},
    }
    stream_settings.update(dict(_XRAY_VLESS_STREAM_SETTINGS_SOCKOPT))
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
        "streamSettings": stream_settings,
    }


def _competitor_dns() -> dict[str, Any]:
    return {
        "disableCache": False,
        "disableFallback": False,
        "disableFallbackIfMatch": True,
        "enableParallelQuery": False,
        "queryStrategy": "UseIPv4",
        "serveExpiredTTL": 0,
        "serveStale": True,
        "servers": ["1.1.1.1", "8.8.8.8"],
        "tag": _COMPETITOR_DNS_TAG,
        "useSystemHosts": False,
    }


def _competitor_policy() -> dict[str, Any]:
    return {
        "levels": {
            "0": {
                "connIdle": 30,
                "handshake": 8,
                "bufferSize": 8,
                "uplinkOnly": 2,
                "downlinkOnly": 2,
            }
        }
    }


def _competitor_inbounds() -> list[dict[str, Any]]:
    return [
        {
            "tag": "socks",
            "port": 10808,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"udp": True, "auth": "noauth"},
            "sniffing": _COMPETITOR_SNIFFING,
        },
        {
            "tag": "http",
            "port": 10809,
            "listen": "127.0.0.1",
            "protocol": "http",
            "settings": {"allowTransparent": False},
            "sniffing": _COMPETITOR_SNIFFING,
        },
    ]


def _competitor_log() -> dict[str, Any]:
    return {
        "loglevel": "Warning",
        "dnsLog": True,
    }


def _competitor_tail_outbounds() -> list[dict[str, Any]]:
    return [
        {"tag": "block", "protocol": "blackhole"},
        {"tag": "direct", "protocol": "freedom"},
    ]


def _least_load_costs(pool: list[Server], *, whitelist: bool) -> list[dict[str, Any]]:
    """Меньше ``load_percent`` — меньше cost (предпочтительнее для leastLoad)."""
    costs: list[dict[str, Any]] = []
    for s in pool:
        tag = competitor_outbound_tag(s.id, whitelist=whitelist)
        costs.append(
            {
                "match": tag,
                "value": max(1, int(s.load_percent) + 1),
                "regexp": False,
            }
        )
    return costs


def _tiered_rec_wl_costs(pool_rec: list[Server], wl: Server) -> list[dict[str, Any]]:
    """
    Приоритет regular (меньший cost), WL — запасной (больший cost).

    При недоступности rec observatory + leastLoad переключаются на WL.
    """
    costs: list[dict[str, Any]] = []
    for s in pool_rec:
        tag = competitor_outbound_tag(s.id, whitelist=False)
        costs.append(
            {
                "match": tag,
                "value": max(1, int(s.load_percent) + 1),
                "regexp": False,
            }
        )
    wl_tag = competitor_outbound_tag(wl.id, whitelist=True)
    costs.append({"match": wl_tag, "value": 100, "regexp": False})
    return costs


def _competitor_routing(
    *,
    member_tags: list[str],
    fallback_tag: str,
    balancer_tag: str = _COMPETITOR_BALANCER_TAG,
    pool_for_costs: list[Server] | None = None,
    costs_whitelist: bool = False,
    tiered_costs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    strategy: dict[str, Any] = {"type": "leastLoad"}
    if tiered_costs:
        strategy["settings"] = {
            "costs": tiered_costs,
            "maxRTT": "10s",
            "expected": 1,
        }
    elif pool_for_costs and len(pool_for_costs) > 1:
        strategy["settings"] = {
            "costs": _least_load_costs(pool_for_costs, whitelist=costs_whitelist),
            "maxRTT": "10s",
            "expected": 1,
        }

    rules: list[dict[str, Any]] = [
        {
            "type": "field",
            "inboundTag": [_COMPETITOR_DNS_TAG],
            "balancerTag": balancer_tag,
        },
        {
            "type": "field",
            "outboundTag": "direct",
            "port": _DIRECT_SERVICE_PORTS,
        },
        {
            "type": "field",
            "domain": ["geosite:category-block"],
            "outboundTag": "block",
        },
        {
            "type": "field",
            "domain": ["geosite:category-proxy"],
            "balancerTag": balancer_tag,
        },
        {
            "type": "field",
            "domain": ["geosite:category-direct"],
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
            "balancerTag": balancer_tag,
        },
    ]

    return {
        "domainMatcher": "hybrid",
        "domainStrategy": "IPIfNonMatch",
        "rules": rules,
        "balancers": [
            {
                "tag": balancer_tag,
                "selector": list(member_tags),
                "strategy": strategy,
                "fallbackTag": fallback_tag,
            }
        ],
    }


def _competitor_observatory(subject_tags: list[str]) -> dict[str, Any]:
    return {
        "enableConcurrency": True,
        "probeInterval": _COMPETITOR_PROBE_INTERVAL,
        "probeUrl": _COMPETITOR_PROBE_URL,
        "subjectSelector": list(subject_tags),
    }


def build_happ_competitor_balanced_profile_json(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    pool_whitelist: bool,
    fallback_server: Server | None = None,
    balancer_tag: str = _COMPETITOR_BALANCER_TAG,
) -> str | None:
    """
    Один JSON-профиль: ``pool`` в balancer (``leastLoad``), опциональный WL/rec fallback outbound.

    - ``pool`` — узлы в ``selector`` балансировщика (обычно ``pool_rec``).
    - ``fallback_server`` — отдельный outbound (обычно лучший WL), ``fallbackTag`` балансировщика.
    """
    if not pool:
        return None

    member_tags: list[str] = []
    proxy_outbounds: list[dict[str, Any]] = []

    for s in pool:
        tag = competitor_outbound_tag(s.id, whitelist=pool_whitelist)
        ob = server_to_competitor_vless_outbound(
            s,
            client_uuid=client_uuid,
            tag=tag,
            client_fingerprint=fp_by_id[s.id],
        )
        if ob is None:
            continue
        member_tags.append(tag)
        proxy_outbounds.append(ob)

    if not member_tags:
        return None

    fallback_tag = member_tags[0]
    observatory_tags = list(member_tags)

    if fallback_server is not None:
        fb_whitelist = bool(fallback_server.whitelist)
        fb_tag = competitor_outbound_tag(fallback_server.id, whitelist=fb_whitelist)
        if fb_tag not in member_tags:
            fb_ob = server_to_competitor_vless_outbound(
                fallback_server,
                client_uuid=client_uuid,
                tag=fb_tag,
                client_fingerprint=fp_by_id[fallback_server.id],
            )
            if fb_ob is not None:
                proxy_outbounds.append(fb_ob)
                fallback_tag = fb_tag
                observatory_tags.append(fb_tag)
                member_tags.append(fb_tag)

    tiered_costs = (
        _tiered_rec_wl_costs(pool, fallback_server)
        if fallback_server is not None
        else None
    )
    outbounds = [*proxy_outbounds, *_competitor_tail_outbounds()]
    routing = _competitor_routing(
        member_tags=member_tags,
        fallback_tag=fallback_tag,
        balancer_tag=balancer_tag,
        pool_for_costs=pool if len(pool) > 1 and tiered_costs is None else None,
        costs_whitelist=pool_whitelist,
        tiered_costs=tiered_costs,
    )

    doc: dict[str, Any] = {
        "dns": _competitor_dns(),
        "policy": _competitor_policy(),
        "remarks": remark,
        "routing": routing,
        "inbounds": _competitor_inbounds(),
        "log": _competitor_log(),
        "outbounds": outbounds,
        "observatory": _competitor_observatory(observatory_tags),
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def build_happ_plain_vless_profile(
    remark: str,
    server: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    """Один узел: outbound ``proxy``, без balancer и observatory."""
    proxy = server_to_competitor_vless_outbound(
        server,
        client_uuid=client_uuid,
        tag="proxy",
        client_fingerprint=client_fingerprint,
    )
    if proxy is None:
        return None
    return {
        "dns": _competitor_dns(),
        "policy": _competitor_policy(),
        "remarks": remark,
        "inbounds": _competitor_inbounds(),
        "log": _competitor_log(),
        "outbounds": [proxy, *_competitor_tail_outbounds()],
        "routing": {
            "domainMatcher": "hybrid",
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": [_COMPETITOR_DNS_TAG],
                    "outboundTag": "proxy",
                },
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
        },
    }


def build_happ_competitor_balanced_profile(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    pool_whitelist: bool,
    fallback_server: Server | None = None,
    balancer_tag: str = _COMPETITOR_BALANCER_TAG,
) -> dict[str, Any] | None:
    """Тот же профиль, что ``build_happ_competitor_balanced_profile_json``, как dict."""
    line = build_happ_competitor_balanced_profile_json(
        remark,
        pool,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=pool_whitelist,
        fallback_server=fallback_server,
        balancer_tag=balancer_tag,
    )
    if line is None:
        return None
    return json.loads(line)
