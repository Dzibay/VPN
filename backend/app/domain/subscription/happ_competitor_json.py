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
    _subscription_utls_fingerprint,
    _xhttp_extra,
    _xhttp_path_for_server,
    _xhttp_vkcdn_extra,
    _primary_sni,
    _tls_sni_for_server,
)
from app.infrastructure.persistence.models.server import Server

_COMPETITOR_BALANCER_TAG = "auto-balance"
_COMPETITOR_PROBE_URL = "http://1.1.1.1/generate_204"
YOUTUBE_PROBE_URL = "https://www.youtube.com/generate_204"
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
_WL_AUTO_COST = 100


def competitor_outbound_tag(server_id: int, *, whitelist: bool) -> str:
    prefix = "wl" if whitelist else "rec"
    return f"{prefix}-{int(server_id)}"


def _hysteria2_password_for_server(s: Server) -> str:
    return ((s.vless_uuid or "").replace("-", "")[:32] or f"hysteria{int(s.id)}")


def server_to_competitor_hysteria2_outbound(
    s: Server,
    *,
    tag: str,
) -> dict[str, Any] | None:
    host = (s.host or "").strip()
    if not host:
        return None
    return {
        "tag": tag,
        "protocol": "hysteria2",
        "settings": {
            "servers": [
                {
                    "address": host,
                    "port": int(s.port),
                    "password": _hysteria2_password_for_server(s),
                }
            ]
        },
        "streamSettings": {
            "network": "udp",
            "security": "tls",
            "tlsSettings": {
                "serverName": host,
                "allowInsecure": True,
            },
        },
    }


def server_to_competitor_vless_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    """VLESS outbound: REALITY TCP или gRPC+TLS."""
    kind = (s.proxy_kind or "vless").strip().lower()
    if kind == "vless_grpc":
        return server_to_competitor_vless_grpc_outbound(
            s,
            client_uuid=client_uuid,
            tag=tag,
        )
    if kind == "vless_ws":
        return server_to_competitor_vless_ws_outbound(
            s,
            client_uuid=client_uuid,
            tag=tag,
        )
    if kind == "vless_xhttp":
        return server_to_competitor_vless_xhttp_outbound(
            s,
            client_uuid=client_uuid,
            tag=tag,
            client_fingerprint=client_fingerprint,
        )
    if kind == "vless_vk_cdn_xhttp":
        return server_to_competitor_vless_vkcdn_xhttp_outbound(
            s,
            client_uuid=client_uuid,
            tag=tag,
            client_fingerprint=client_fingerprint,
        )
    return server_to_competitor_vless_reality_outbound(
        s,
        client_uuid=client_uuid,
        tag=tag,
        client_fingerprint=client_fingerprint,
    )


def server_to_competitor_vless_grpc_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
) -> dict[str, Any] | None:
    host = (s.host or "").strip()
    uid = (client_uuid or "").strip()
    sni = _tls_sni_for_server(s)
    service_name = (s.grpc_service_name or "grpc").strip()
    if not host or not uid or not sni or not service_name:
        return None
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
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": "grpc",
            "security": "tls",
            "tlsSettings": {
                "serverName": sni,
                "allowInsecure": False,
                "alpn": ["h2"],
            },
            "grpcSettings": {
                "serviceName": service_name,
                "multiMode": False,
            },
        },
    }


def server_to_competitor_vless_ws_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
) -> dict[str, Any] | None:
    host = (s.host or "").strip()
    uid = (client_uuid or "").strip()
    sni = _tls_sni_for_server(s)
    wpath = (s.ws_path or "/vless").strip() or "/vless"
    if not wpath.startswith("/"):
        wpath = "/" + wpath
    if not host or not uid or not sni:
        return None
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": int(s.port),
                    "users": [{"id": uid, "encryption": "none"}],
                }
            ]
        },
        "streamSettings": {
            "network": "ws",
            "security": "tls",
            "tlsSettings": {
                "serverName": sni,
                "allowInsecure": False,
                "alpn": ["http/1.1"],
            },
            "wsSettings": {"path": wpath},
        },
    }


def server_to_competitor_vless_xhttp_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    host = (s.host or "").strip()
    uid = (client_uuid or "").strip()
    sni = _tls_sni_for_server(s)
    if not host or not uid or not sni:
        return None
    path = _xhttp_path_for_server(s)
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": int(s.port),
                    "users": [{"id": uid, "encryption": "none"}],
                }
            ]
        },
        "streamSettings": {
            "network": "xhttp",
            "security": "tls",
            "tlsSettings": {
                "serverName": sni,
                "fingerprint": _subscription_utls_fingerprint(client_fingerprint),
                "allowInsecure": False,
                "alpn": ["h3", "h2", "http/1.1"],
            },
            "xhttpSettings": {
                "path": path,
                "mode": "packet-up",
                "host": sni,
                "extra": _xhttp_extra(path),
            },
        },
    }


def server_to_competitor_vless_vkcdn_xhttp_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    cdn = (s.cdn_domain or "").strip().rstrip(".")
    uid = (client_uuid or "").strip()
    if not cdn or not uid:
        return None
    path = _xhttp_path_for_server(s)
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": cdn,
                    "port": int(s.port),
                    "users": [{"id": uid, "encryption": "none"}],
                }
            ]
        },
        "streamSettings": {
            "network": "xhttp",
            "security": "tls",
            "tlsSettings": {
                "serverName": cdn,
                "fingerprint": _subscription_utls_fingerprint(client_fingerprint),
                "allowInsecure": False,
                "alpn": ["h3", "h2", "http/1.1"],
            },
            "xhttpSettings": {
                "host": cdn,
                "path": path,
                "mode": "packet-up",
                "extra": _xhttp_vkcdn_extra(path),
            },
        },
    }


def server_to_competitor_vless_reality_outbound(
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
    fp = _subscription_utls_fingerprint(client_fingerprint)
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
    # DNS на клиенте Happ. Оба сервера — local-режим (минуя routing), иначе
    # запросы попадают в catch-all ``proxy``, нет VLESS-handshake → нет резолва →
    # «бесконечная загрузка» всех сайтов.
    #
    # 1) udp+local 77.88.8.8 — RU TLD (.ru/.su/.рф). Без geosite:* — Happ резолвит
    #    DNS до загрузки geosite.dat (см. «category-ru / missing file» при коннекте).
    # 2) https+local 1.1.1.1 — всё остальное. ``+local`` важно: Xray ходит за DoH
    #    через freedom-outbound напрямую, без VPN/прокси. Иначе при недоступном
    #    proxy DoH тоже мёртв.
    return {
        "disableCache": False,
        "disableFallback": False,
        "disableFallbackIfMatch": True,
        "enableParallelQuery": False,
        "queryStrategy": "UseIPv4",
        "serveExpiredTTL": 0,
        "serveStale": True,
        "servers": [
            {
                "domains": [
                    "regexp:.*\\.ru$",
                    "regexp:.*\\.su$",
                    "regexp:.*\\.xn--p1ai$",
                ],
                "address": "udp+local://77.88.8.8",
                "timeoutMs": 2000,
                "skipFallback": False,
            },
            {
                "address": "https+local://1.1.1.1/dns-query",
                "timeoutMs": 5000,
            },
        ],
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


def _auto_mixed_pool_costs(pool: list[Server]) -> list[dict[str, Any]]:
    """Auto-группа: rec — по нагрузке, WL — повышенный cost (резерв)."""
    costs: list[dict[str, Any]] = []
    for s in pool:
        tag = competitor_outbound_tag(s.id, whitelist=bool(s.whitelist))
        if s.whitelist:
            costs.append({"match": tag, "value": _WL_AUTO_COST, "regexp": False})
        else:
            costs.append(
                {
                    "match": tag,
                    "value": max(1, int(s.load_percent) + 1),
                    "regexp": False,
                }
            )
    return costs


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
    costs.append({"match": wl_tag, "value": _WL_AUTO_COST, "regexp": False})
    return costs


def _first_valid_vless_in_pool(
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> Server | None:
    for s in pool:
        if server_to_competitor_vless_outbound(
            s,
            client_uuid=client_uuid,
            tag=competitor_outbound_tag(s.id, whitelist=bool(s.whitelist)),
            client_fingerprint=fp_by_id[s.id],
        ):
            return s
    return None


def _fallback_tag_prefer_wl(pool: list[Server], member_tags: list[str]) -> str:
    """
    fallbackTag балансировщика: предпочитаем WL-узел (РФ, доступен и при белых списках).

    Для leastLoad узлы без данных observatory исключаются, и до первого замера (или когда
    все зарубежные узлы недоступны) балансировщик использует fallbackTag — он обязан вести
    на доступный узел. WL-узел работает и в обычном режиме, и при белых списках, поэтому
    он безопаснее зарубежного как «последний резерв».
    """
    for s in pool:
        if s.whitelist:
            tag = competitor_outbound_tag(s.id, whitelist=True)
            if tag in member_tags:
                return tag
    for s in pool:
        if not s.whitelist:
            tag = competitor_outbound_tag(s.id, whitelist=False)
            if tag in member_tags:
                return tag
    return member_tags[0]


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
        # Страховка: встроенный DNS никогда не идёт через balancer/proxy.
        {
            "type": "field",
            "inboundTag": [_COMPETITOR_DNS_TAG],
            "outboundTag": "direct",
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


def _competitor_observatory(
    subject_tags: list[str],
    *,
    probe_url: str = _COMPETITOR_PROBE_URL,
) -> dict[str, Any]:
    return {
        "enableConcurrency": True,
        "probeInterval": _COMPETITOR_PROBE_INTERVAL,
        "probeUrl": probe_url,
        "subjectSelector": list(subject_tags),
    }


def _balanced_profile_doc(
    *,
    remark: str,
    member_tags: list[str],
    proxy_outbounds: list[dict[str, Any]],
    observatory_tags: list[str],
    fallback_tag: str,
    balancer_tag: str,
    tiered_costs: list[dict[str, Any]] | None,
    pool_for_costs: list[Server] | None,
    costs_whitelist: bool,
    probe_url: str = _COMPETITOR_PROBE_URL,
) -> dict[str, Any]:
    outbounds = [*proxy_outbounds, *_competitor_tail_outbounds()]
    routing = _competitor_routing(
        member_tags=member_tags,
        fallback_tag=fallback_tag,
        balancer_tag=balancer_tag,
        pool_for_costs=pool_for_costs,
        costs_whitelist=costs_whitelist,
        tiered_costs=tiered_costs,
    )
    return {
        "dns": _competitor_dns(),
        "policy": _competitor_policy(),
        "remarks": remark,
        "routing": routing,
        "inbounds": _competitor_inbounds(),
        "log": _competitor_log(),
        "outbounds": outbounds,
        "observatory": _competitor_observatory(observatory_tags, probe_url=probe_url),
    }


def build_happ_auto_group_balanced_profile(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    balancer_tag: str,
    probe_url: str = _COMPETITOR_PROBE_URL,
) -> dict[str, Any] | None:
    """
    Auto-группа: все ``include_in_auto`` VLESS узлы в одном профиле.

    Cost: rec — по нагрузке, WL — повышенный (резерв).
    ``probe_url`` — URL observatory (по умолчанию общий generate_204).
  """
    if not pool:
        return None

    member_tags: list[str] = []
    proxy_outbounds: list[dict[str, Any]] = []

    for s in pool:
        tag = competitor_outbound_tag(s.id, whitelist=bool(s.whitelist))
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

    if len(member_tags) < 2:
        primary = _first_valid_vless_in_pool(pool, client_uuid=client_uuid, fp_by_id=fp_by_id)
        if primary is None:
            return None
        return build_happ_plain_vless_profile(
            remark,
            primary,
            client_uuid=client_uuid,
            client_fingerprint=fp_by_id[primary.id],
        )

    return _balanced_profile_doc(
        remark=remark,
        member_tags=member_tags,
        proxy_outbounds=proxy_outbounds,
        observatory_tags=list(member_tags),
        fallback_tag=_fallback_tag_prefer_wl(pool, member_tags),
        balancer_tag=balancer_tag,
        tiered_costs=_auto_mixed_pool_costs(pool),
        pool_for_costs=None,
        costs_whitelist=False,
        probe_url=probe_url,
    )


def build_happ_tiered_wl_balanced_profile(
    remark: str,
    pool_rec: list[Server],
    wl: Server,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    balancer_tag: str,
) -> dict[str, Any] | None:
    """
    Tiered WL профиль: rec (основной пул) + один WL outbound (резерв).

    Cost: rec — по нагрузке, WL — повышенный (резерв).
    """
    if not pool_rec or not wl:
        return None

    member_tags: list[str] = []
    proxy_outbounds: list[dict[str, Any]] = []

    for s in pool_rec:
        tag = competitor_outbound_tag(s.id, whitelist=False)
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

    ob_wl = server_to_competitor_vless_outbound(
        wl,
        client_uuid=client_uuid,
        tag=competitor_outbound_tag(wl.id, whitelist=True),
        client_fingerprint=fp_by_id[wl.id],
    )
    if ob_wl:
        member_tags.append(competitor_outbound_tag(wl.id, whitelist=True))
        proxy_outbounds.append(ob_wl)

    if not member_tags:
        return None

    if len(member_tags) < 2:
        return None

    return _balanced_profile_doc(
        remark=remark,
        member_tags=member_tags,
        proxy_outbounds=proxy_outbounds,
        observatory_tags=list(member_tags),
        fallback_tag=_fallback_tag_prefer_wl([*pool_rec, wl], member_tags),
        balancer_tag=balancer_tag,
        tiered_costs=_tiered_rec_wl_costs(pool_rec, wl),
        pool_for_costs=None,
        costs_whitelist=False,
    )


def _happ_plain_profile_doc(proxy: dict[str, Any], remark: str) -> dict[str, Any]:
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
                # Страховка: трафик встроенного DNS никогда не должен идти в proxy
                # (если local-режим у DNS-сервера почему-то выпал, всё равно direct).
                {
                    "type": "field",
                    "inboundTag": [_COMPETITOR_DNS_TAG],
                    "outboundTag": "direct",
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


def build_happ_plain_vless_profile(
    remark: str,
    server: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    """Один VLESS-узел: outbound ``proxy``, без balancer и observatory."""
    proxy = server_to_competitor_vless_outbound(
        server,
        client_uuid=client_uuid,
        tag="proxy",
        client_fingerprint=client_fingerprint,
    )
    if proxy is None:
        return None
    return _happ_plain_profile_doc(proxy, remark)


def build_happ_plain_hysteria2_profile(remark: str, server: Server) -> dict[str, Any] | None:
    """Один Hysteria2-узел: outbound ``proxy``, без balancer."""
    proxy = server_to_competitor_hysteria2_outbound(server, tag="proxy")
    if proxy is None:
        return None
    return _happ_plain_profile_doc(proxy, remark)


def build_happ_plain_server_profile(
    remark: str,
    server: Server,
    *,
    client_uuid: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    """Прямой JSON-профиль узла (VLESS или Hysteria2)."""
    kind = (server.proxy_kind or "vless").strip().lower()
    if kind == "hysteria2":
        return build_happ_plain_hysteria2_profile(remark, server)
    return build_happ_plain_vless_profile(
        remark,
        server,
        client_uuid=client_uuid,
        client_fingerprint=client_fingerprint,
    )


