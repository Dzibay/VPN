#!/usr/bin/env bash
# Каскад РФ-вход → exit: outbound и routing в уже записанный config.json.
# Транспорт exit: VPN_CASCADE_EGRESS_TRANSPORT = vless | vless_grpc | vless_ws

set -euo pipefail

_apply_xray_cascade_to_file() {
  local cfg_path="${1:-${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}}"
  python3 - "$cfg_path" << 'PY'
import json
import os
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)

if (os.environ.get("VPN_CASCADE_ENABLED") or "").strip() != "1":
    sys.exit(0)

inbound_tag = (os.environ.get("VPN_VLESS_INBOUND_TAG") or "vpn-vless-in").strip() or "vpn-vless-in"
ru_direct = (os.environ.get("VPN_CASCADE_RU_DIRECT") or "1").strip() == "1"
transport = (os.environ.get("VPN_CASCADE_EGRESS_TRANSPORT") or "vless").strip().lower()

eaddr = os.environ["VPN_CASCADE_EGRESS_ADDRESS"].strip()
eport = int(os.environ.get("VPN_CASCADE_EGRESS_PORT", "443"))
ecid = os.environ["VPN_CASCADE_EGRESS_CLIENT_UUID"].strip()

user = {"id": ecid, "encryption": "none"}

if transport == "vless":
    flow = os.environ.get("VPN_CASCADE_EGRESS_FLOW", "xtls-rprx-vision").strip() or "xtls-rprx-vision"
    user["flow"] = flow
    sn0 = (
        [x.strip() for x in os.environ.get("VPN_CASCADE_EGRESS_SERVER_NAMES", "").split(",") if x.strip()]
        or ["www.amazon.com"]
    )[0]
    efp = os.environ.get("VPN_CASCADE_EGRESS_FINGERPRINT", "chrome").strip() or "chrome"
    esid = os.environ.get("VPN_CASCADE_EGRESS_SHORT_ID", "").strip() or "ab"
    epbk = os.environ["VPN_CASCADE_EGRESS_PBK"].strip()
    _eg_spider = (os.environ.get("VPN_CASCADE_EGRESS_SPIDER_X") or "/").strip() or "/"
    if not _eg_spider.startswith("/"):
        _eg_spider = "/" + _eg_spider.lstrip("/")
    _eg_spider = _eg_spider[:256]
    stream = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "show": False,
            "fingerprint": efp,
            "serverName": sn0,
            "publicKey": epbk,
            "shortId": esid,
            "spiderX": _eg_spider,
        },
        "sockopt": {
            "tcpFastOpen": True,
            "tcpcongestion": "bbr",
            "happyEyeballs": {
                "interleave": 1,
                "tryDelayMs": 250,
                "prioritizeIPv6": False,
                "maxConcurrentTry": 4,
            },
        },
    }
elif transport == "vless_grpc":
    sni = (os.environ.get("VPN_CASCADE_EGRESS_TLS_SNI") or eaddr).strip()
    svc = (os.environ.get("VPN_CASCADE_EGRESS_GRPC_SERVICE") or "grpc").strip() or "grpc"
    stream = {
        "network": "grpc",
        "security": "tls",
        "tlsSettings": {"serverName": sni, "alpn": ["h2"]},
        "grpcSettings": {"serviceName": svc, "multiMode": False},
    }
elif transport == "vless_ws":
    sni = (os.environ.get("VPN_CASCADE_EGRESS_TLS_SNI") or eaddr).strip()
    wpath = (os.environ.get("VPN_CASCADE_EGRESS_WS_PATH") or "/vless").strip() or "/vless"
    if not wpath.startswith("/"):
        wpath = "/" + wpath
    stream = {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {"serverName": sni, "alpn": ["http/1.1"]},
        "wsSettings": {"path": wpath},
    }
else:
    raise SystemExit("VPN_CASCADE_EGRESS_TRANSPORT: %s" % transport)

vless_to_exit = {
    "tag": "egress-cascade",
    "protocol": "vless",
    "settings": {
        "vnext": [
            {
                "address": eaddr,
                "port": eport,
                "users": [user],
            }
        ]
    },
    "streamSettings": stream,
}

cfg["outbounds"] = [
    vless_to_exit,
    {"protocol": "freedom", "tag": "direct", "settings": {"domainStrategy": "UseIPv4"}},
    {"protocol": "blackhole", "tag": "block"},
]

gemini_domains = [
    "domain:gemini.google.com",
    "domain:aistudio.google.com",
    "domain:clients6.google.com",
    "domain:generativelanguage.googleapis.com",
    "domain:alkalimining-pa.googleapis.com",
    "domain:proactivebackend-pa.googleapis.com",
]
gemini_rule = {"type": "field", "outboundTag": "egress-cascade", "domain": gemini_domains}
gemini_google_ip_rule = {"type": "field", "outboundTag": "egress-cascade", "ip": ["geoip:google"]}
dns_outbound_tag = "egress-cascade"

raw_extra_ru = (os.environ.get("VPN_CASCADE_RU_DIRECT_EXTRA_DOMAINS") or "vk.com").strip()
extra_ru_domains = []
if raw_extra_ru:
    seen = set()
    for token in re.split(r"[\s,;]+", raw_extra_ru):
        t = token.strip()
        if not t:
            continue
        if ":" not in t:
            t = "domain:%s" % t.lstrip(".")
        if t not in seen:
            seen.add(t)
            extra_ru_domains.append(t)

if ru_direct:
    _ru_domains = [
        "geosite:private",
        *extra_ru_domains,
        "geosite:category-ru",
        "regexp:.*\\.ru$",
        "regexp:.*\\.su$",
        "regexp:.*\\.xn--p1ai$",
    ]
    cfg["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            gemini_rule,
            gemini_google_ip_rule,
            {"type": "field", "outboundTag": "direct", "domain": _ru_domains},
            {"type": "field", "outboundTag": "direct", "ip": ["geoip:ru", "geoip:private"]},
            {
                "type": "field",
                "inboundTag": [inbound_tag],
                "outboundTag": "egress-cascade",
            },
        ],
    }
else:
    cfg["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            gemini_rule,
            gemini_google_ip_rule,
            {
                "type": "field",
                "inboundTag": [inbound_tag],
                "outboundTag": "egress-cascade",
            },
        ],
    }

dns_ru_domains = [
    "geosite:private",
    "geosite:category-ru",
    "regexp:.*\\.ru$",
    "regexp:.*\\.su$",
    "regexp:.*\\.xn--p1ai$",
]
if ru_direct:
    dns_ru_domains = [*dns_ru_domains, *extra_ru_domains]

cfg["dns"] = {
    "servers": [
        {
            "address": "https://1.1.1.1/dns-query",
            "domains": ["geosite:geolocation-!cn"],
            "skipFallback": True,
            "clientIP": "1.1.1.1",
        },
        {
            "address": "77.88.8.8",
            "domains": dns_ru_domains,
            "expectIPs": ["geoip:ru"],
            "skipFallback": True,
        },
        "8.8.8.8",
    ],
    "queryStrategy": "UseIPv4",
    "tag": "dns-inbound",
}

dns_rules = [
    {
        "type": "field",
        "inboundTag": ["dns-inbound"],
        "outboundTag": dns_outbound_tag,
        "domain": ["geosite:geolocation-!cn"],
    },
    {
        "type": "field",
        "inboundTag": ["dns-inbound"],
        "outboundTag": "direct",
        "domain": dns_ru_domains,
    },
]
quic_block_rule = {
    "type": "field",
    "outboundTag": "block",
    "network": "udp",
    "port": "443",
    "domain": ["geosite:geolocation-!cn"],
}
cfg["routing"]["rules"] = [*dns_rules, *cfg["routing"]["rules"], quic_block_rule]

with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
PY
}
