#!/usr/bin/env bash
# Установка и обслуживание VLESS+REALITY через Xray.

set -euo pipefail

# x25519: разбор вывода `xray x25519` / `xray x25519 -i`.
# Xray-core (curve25519.go): «PrivateKey: …», «Password (PublicKey): …», «Hash32: …» — публичный ключ в строке Password (PublicKey), не «Password:».
# Старый формат: Private key / Public key.
# set -o pipefail: в конвейере нужен || true.
_x25519_line() {
  local out="$1"
  local pattern="$2"
  echo "$out" | grep -iE "^[[:space:]]*${pattern}[[:space:]]*:" | head -1 \
    | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]+$//' || true
}

_x25519_pick_private() {
  local out="$1"
  local v
  v=$(_x25519_line "$out" "PrivateKey")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  v=$(_x25519_line "$out" "Private[[:space:]]+key")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  echo ""
}

_x25519_pick_public() {
  local out="$1"
  local v
  v=$(_x25519_line "$out" "PublicKey")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  v=$(_x25519_line "$out" "Public[[:space:]]+key")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  # Актуальный Xray: «Password (PublicKey):» — не «Password:».
  v=$(_x25519_line "$out" "Password[[:space:]]*\(PublicKey\)")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  v=$(_x25519_line "$out" "Password")
  if [[ -n "$v" ]]; then echo "$v"; return 0; fi
  echo ""
}

# Клиенты: VPN_VLESS_CLIENTS_B64 (base64 JSON [{id,email,flow,level},…]) или legacy VPN_VLESS_CLIENT_UUIDS.
# Stats API: упрощённый режим Xray (api.listen), без dokodemo-door + routing.
# См. https://xtls.github.io/en/config/api.html — иначе `xray api statsquery` даёт failed to dial.
_write_xray_config() {
  local file_path raw=""
  file_path="${VPN_CASCADE_RU_DIRECT_DOMAINS_FILE:-${SCRIPT_DIR}/ru_direct_extra_domains.txt}"
  if [[ -f "$file_path" ]]; then
    # Файл: по одному домену/правилу на строку; пустые строки и комментарии игнорируются.
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="$(echo "$line" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')"
      [[ -n "$line" ]] || continue
      raw+="${raw:+,}${line}"
    done < "$file_path"
  fi
  if [[ -n "$raw" ]]; then
    export VPN_CASCADE_RU_DIRECT_EXTRA_DOMAINS="$raw"
  fi
  python3 - << 'PY'
import base64
import json
import os
import re

port = int(os.environ["VPN_SERVER_PORT"])
api_port = int(os.environ.get("VPN_XRAY_API_PORT") or "10085")
fallback_uid = os.environ["VPN_VLESS_UUID"].strip()
flow_def = os.environ.get("VPN_VLESS_FLOW", "xtls-rprx-vision")
inbound_tag = (os.environ.get("VPN_VLESS_INBOUND_TAG") or "vpn-vless-in").strip() or "vpn-vless-in"

b64 = (os.environ.get("VPN_VLESS_CLIENTS_B64") or "").strip()
clients = []
if b64:
    try:
        clients = json.loads(base64.b64decode(b64).decode("utf-8"))
    except Exception:
        clients = []
if not clients:
    raw = (os.environ.get("VPN_VLESS_CLIENT_UUIDS") or "").strip()
    if raw:
        uuids = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        uuids = [fallback_uid]
    seen = set()
    uuids_deduped = []
    for u in uuids:
        if u not in seen:
            seen.add(u)
            uuids_deduped.append(u)
    uuids = uuids_deduped or [fallback_uid]
    for i, u in enumerate(uuids):
        clients.append(
            {
                "id": u,
                "flow": flow_def,
                "email": "u%d@vpn" % i,
                "level": 0,
            }
        )

dest = os.environ["VPN_REALITY_DEST"]
names = [x.strip() for x in os.environ["VPN_REALITY_SERVER_NAMES"].split(",") if x.strip()]
fp = os.environ.get("VPN_REALITY_FINGERPRINT", "chrome")
flow = flow_def
short_id = os.environ["VPN_REALITY_SHORT_ID"].strip()
priv = os.environ["VPN_REALITY_PRIVATE_KEY"]

short_ids = ["", short_id] if short_id else [""]

_reality_spider_x = (os.environ.get("VPN_REALITY_SPIDER_X") or "/").strip() or "/"
if not _reality_spider_x.startswith("/"):
    _reality_spider_x = "/" + _reality_spider_x.lstrip("/")
_reality_spider_x = _reality_spider_x[:256]

for c in clients:
    if "flow" not in c:
        c["flow"] = flow
    if "level" not in c:
        c["level"] = 0
    if "email" not in c:
        c["email"] = "u0@vpn"

cfg = {
    "log": {"loglevel": "warning"},
    "stats": {},
    "api": {
        "tag": "api",
        "listen": "127.0.0.1:%d" % api_port,
        "services": ["StatsService", "HandlerService"],
    },
    # Level 0: таймауты мягче «агрессивных» 30s у конкурентов; bufferSize 16 (КБ) — ровнее видео при CAKE.
    "policy": {
        "levels": {
            "0": {
                "statsUserUplink": True,
                "statsUserDownlink": True,
                "handshake": 4,
                "connIdle": 300,
                "uplinkOnly": 2,
                "downlinkOnly": 5,
                "bufferSize": 16,
            }
        }
    },
    "inbounds": [
        {
            "tag": inbound_tag,
            "listen": "0.0.0.0",
            "port": port,
            "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "dest": dest,
                    "xver": 0,
                    "serverNames": names,
                    "privateKey": priv,
                    "shortIds": short_ids,
                    "fingerprint": fp,
                    "spiderX": _reality_spider_x,
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
            },
        },
    ],
    "outbounds": [
        {"protocol": "freedom", "tag": "direct", "settings": {"domainStrategy": "UseIPv4"}},
    ],
}

cascade = (os.environ.get("VPN_CASCADE_ENABLED") or "").strip() == "1"
ru_direct = cascade and (os.environ.get("VPN_CASCADE_RU_DIRECT") or "1").strip() == "1"
# routeOnly=True: домен из sniff только для routing (RU/не-RU, Gemini); целевой адрес пакета не подменяется —
# меньше поломок push/банков при обращении по IP или чувствительных TLS. Каскаду нужен стабильный match по домену.
cfg["inbounds"][0]["sniffing"] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
    "routeOnly": True,
}

gemini_domains = [
    "domain:gemini.google.com",
    "domain:aistudio.google.com",
    "domain:clients6.google.com",  # grpc-web: ogads-pa / waa-pa → AsyncDataService, и т.д.
    "domain:generativelanguage.googleapis.com",
    "domain:alkalimining-pa.googleapis.com",
    "domain:proactivebackend-pa.googleapis.com",
]
gemini_tag = "egress-cascade" if cascade else "direct"
dns_outbound_tag = "egress-cascade" if cascade else "direct"
gemini_rule = {
    "type": "field",
    "outboundTag": gemini_tag,
    "domain": gemini_domains,
}
# Трафик на IP из списка google в geoip.dat (QUIC/без домена). Нужен geoip с тегом google (стандартный geoip.dat от install-release).
gemini_google_ip_rule = {
    "type": "field",
    "outboundTag": gemini_tag,
    "ip": ["geoip:google"],
}

# Каскад: РФ-вход — user traffic VLESS+REALITY inbound → VLESS+REALITY outbound на внешний exit
if cascade:
    raw_extra_ru = (os.environ.get("VPN_CASCADE_RU_DIRECT_EXTRA_DOMAINS") or "vk.com").strip()
    extra_ru_domains = []
    if raw_extra_ru:
        seen = set()
        for token in re.split(r"[\s,;]+", raw_extra_ru):
            t = token.strip()
            if not t:
                continue
            # Xray domain rule items may be prefixed (domain:, full:, regexp:, geosite:, keyword:).
            if ":" not in t:
                t = "domain:%s" % t.lstrip(".")
            if t not in seen:
                seen.add(t)
                extra_ru_domains.append(t)

    eg_sni_list = [
        x.strip()
        for x in os.environ.get("VPN_CASCADE_EGRESS_SERVER_NAMES", "").split(",")
        if x.strip()
    ]
    sn0 = eg_sni_list[0] if eg_sni_list else "www.amazon.com"
    eaddr = os.environ["VPN_CASCADE_EGRESS_ADDRESS"].strip()
    eport = int(os.environ.get("VPN_CASCADE_EGRESS_PORT", "443"))
    ecid = os.environ["VPN_CASCADE_EGRESS_CLIENT_UUID"].strip()
    epbk = os.environ["VPN_CASCADE_EGRESS_PBK"].strip()
    esid = os.environ.get("VPN_CASCADE_EGRESS_SHORT_ID", "").strip() or "ab"
    efp = os.environ.get("VPN_CASCADE_EGRESS_FINGERPRINT", "chrome").strip() or "chrome"
    eflow = os.environ.get("VPN_CASCADE_EGRESS_FLOW", "xtls-rprx-vision").strip() or "xtls-rprx-vision"
    _eg_spider = (os.environ.get("VPN_CASCADE_EGRESS_SPIDER_X") or "/").strip() or "/"
    if not _eg_spider.startswith("/"):
        _eg_spider = "/" + _eg_spider.lstrip("/")
    _eg_spider = _eg_spider[:256]
    vless_to_exit = {
        "tag": "egress-cascade",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": eaddr,
                    "port": eport,
                    "users": [
                        {
                            "id": ecid,
                            "encryption": "none",
                            "flow": eflow,
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
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
        },
    }
    direct_out = {
        "protocol": "freedom",
        "tag": "direct",
        "settings": {"domainStrategy": "UseIPv4"},
    }
    blackhole_out = {"protocol": "blackhole", "tag": "block"}
    cfg["outbounds"] = [vless_to_exit, direct_out, blackhole_out]
    cfg["inbounds"][0]["tag"] = "vless-in"
    # РФ-ресурсы: прямой выход; остальное (иностранные) — через VLESS к exit
    if ru_direct:
        # geosite:category-ru — список CATEGORY-RU в geosite.dat (не geosite:ru: в стандартном dat нет кода RU).
        # regexp по TLD — домены .ru вне списка; geoip:ru — IP РФ без домена.
        _ru_domains = [
            "geosite:private",
            *extra_ru_domains,
            "geosite:category-ru",
            "regexp:.*\\.ru$",
            "regexp:.*\\.su$",
            "regexp:.*\\.xn--p1ai$",  # .рф
        ]
        cfg["routing"] = {
            # routing.domainStrategy только AsIs | IPIfNonMatch | IPOnDemand — не UseIPv4 (см. xtls.github.io routing). IPv4: dns.queryStrategy + freedom.
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                gemini_rule,
                gemini_google_ip_rule,
                {
                    "type": "field",
                    "outboundTag": "direct",
                    "domain": _ru_domains,
                },
                {
                    "type": "field",
                    "outboundTag": "direct",
                    "ip": ["geoip:ru", "geoip:private"],
                },
                {
                    "type": "field",
                    "inboundTag": ["vless-in"],
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
                    "inboundTag": ["vless-in"],
                    "outboundTag": "egress-cascade",
                },
            ],
        }
else:
    cfg["outbounds"].append({"protocol": "blackhole", "tag": "block"})
    cfg["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": [gemini_rule, gemini_google_ip_rule],
    }

dns_ru_domains = [
    "geosite:private",
    "geosite:category-ru",
    "regexp:.*\\.ru$",
    "regexp:.*\\.su$",
    "regexp:.*\\.xn--p1ai$",
]
if cascade and ru_direct:
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

path = os.environ.get("VPN_XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY
}

# Каталог для dat (install-release). Списки: geosite:private, geosite:category-ru, regexp TLD, geoip:ru — см. backend/app/geo/geosite.dat
_xray_ensure_geo_dats() {
  if [[ "${VPN_CASCADE_RU_DIRECT:-1}" == "0" ]]; then
    echo "[xray] geo: VPN_CASCADE_RU_DIRECT=0 — dat для split RU не обязателен"
    return 0
  fi
  local dir
  dir="${VPN_XRAY_GEO_DIR:-/usr/local/share/xray}"
  mkdir -p "$dir"
  echo "[xray] geo: split RU — geosite:category-ru + regexp TLD + geoip:ru (dat из XTLS install)"
  return 0
}

# Проверка JSON и маршрутов; иначе systemctl даст мёртвый сокет (TCP connection refused)
_xray_test_config_and_restart() {
  local cfg="$1"
  local xb="${2:-}"
  if [[ -z "$xb" || ! -x "$xb" ]]; then
    xb=$(command -v xray 2>/dev/null) || true
  fi
  if [[ -z "$xb" || ! -x "$xb" ]]; then
    if [[ -x /usr/local/bin/xray ]]; then
      xb=/usr/local/bin/xray
    else
      echo "[xray] нет бинарника xray для run -test" >&2
      return 1
    fi
  fi
  echo "[xray] проверка: $xb run -test -c $cfg"
  if ! "$xb" run -test -c "$cfg" 2>&1; then
    echo "[xray] run -test: конфиг невалиден или нет geosite/geoip (см. выше)" >&2
    return 1
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl restart xray; then
      echo "[xray] systemctl restart xray неудача, последние логи:" >&2
      journalctl -u xray -n 50 --no-pager 2>&1 | head -80 >&2
      return 1
    fi
  else
    echo "[xray] нет systemctl — перезапустите xray вручную" >&2
  fi
  return 0
}

_xray_install() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[xray] нужен python3 для записи config.json" >&2
    exit 1
  fi

  echo "[xray] установка (XTLS install-release.sh)…"
  # Скрипт XTLS в конце включает/запускает xray со своим дефолтным config.json — часто невалиден для узла,
  # systemctl возвращает ошибку, exit≠0, хотя бинарник уже установлен. Дальше мы пишем свой config.json.
  set +e
  bash -c "$(fetch_installer)" @ install
  rc_install=$?
  set -e
  if [[ "$rc_install" -ne 0 ]]; then
    echo "[xray] предупреждение: install-release.sh завершился с кодом $rc_install (часто из-за первого start xray до подмены config); проверяем бинарник…" >&2
  fi
  echo "[xray] install-release.sh код выхода: $rc_install"

  XRAY_BIN=$(command -v xray || true)
  # Не использовать [[ -z ]] && присвоение: при непустом PATH set -e обрывает скрипт на ложном [[.
  if [[ -z "$XRAY_BIN" ]]; then
    XRAY_BIN=/usr/local/bin/xray
  fi
  if [[ ! -x "$XRAY_BIN" ]]; then
    echo "[xray] не найден бинарник xray" >&2
    exit 1
  fi

  if [[ -n "${VPN_REALITY_PRIVATE_KEY:-}" ]]; then
    PRIVATE_KEY=$(echo "${VPN_REALITY_PRIVATE_KEY}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    # Часть сборок пишет ключи в stderr — смотрим оба потока.
    PUB_OUT=$($XRAY_BIN x25519 -i "$PRIVATE_KEY" 2>&1 || true)
    PUBLIC_KEY=$(_x25519_pick_public "$PUB_OUT")
  else
    # set -e: ненулевой код x25519 убил бы скрипт без сообщения
    set +e
    KP=$($XRAY_BIN x25519 2>&1)
    rc_x25519=$?
    set -e
    if [[ "$rc_x25519" -ne 0 ]]; then
      echo "[xray] ошибка: $XRAY_BIN x25519 завершился с кодом $rc_x25519" >&2
      exit 1
    fi
    PRIVATE_KEY=$(_x25519_pick_private "$KP")
    PUBLIC_KEY=$(_x25519_pick_public "$KP")
  fi

  if [[ -z "$PRIVATE_KEY" || -z "$PUBLIC_KEY" ]]; then
    echo "[xray] не удалось получить ключи REALITY (x25519): проверьте формат вывода xray x25519 (нужны PrivateKey и PublicKey или Password)." >&2
    exit 1
  fi

  export VPN_REALITY_PRIVATE_KEY="$PRIVATE_KEY"

  CFG=/usr/local/etc/xray/config.json
  mkdir -p "$(dirname "$CFG")"

  if [[ "${VPN_CASCADE_ENABLED:-0}" == "1" && "${VPN_CASCADE_RU_DIRECT:-1}" != "0" ]]; then
    _xray_ensure_geo_dats || exit 1
  fi

  echo "[xray] запись $CFG (VLESS REALITY → ${VPN_REALITY_DEST})…"
  _write_xray_config
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable xray 2>/dev/null || true
  fi
  _xray_test_config_and_restart "$CFG" "$XRAY_BIN" || exit 1
  _vps_net_sysctl_install || true
}

_xray_sync_clients() {
  CFG="${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}"
  if [[ "${VPN_CASCADE_ENABLED:-0}" == "1" && "${VPN_CASCADE_RU_DIRECT:-1}" != "0" ]]; then
    _xray_ensure_geo_dats || exit 1
  fi
  echo "[xray] sync_clients: запись $CFG (без установки пакета)…"
  _write_xray_config
  # XRAY_BIN задаётся только в _xray_install; при sync_clients и set -u нельзя читать несуществующую переменную.
  XBIN="${XRAY_BIN:-}"
  if [[ -z "$XBIN" || ! -x "$XBIN" ]]; then
    XBIN=$(command -v xray 2>/dev/null) || true
  fi
  if [[ -z "$XBIN" && -x /usr/local/bin/xray ]]; then
    XBIN=/usr/local/bin/xray
  fi
  _xray_test_config_and_restart "$CFG" "$XBIN" || exit 1
  echo "[xray] sync_clients: перезапуск xray выполнен"
}

_xray_cleanup() {
  echo "[cleanup] Xray: remove --purge (XTLS install-release.sh)…"
  set +e
  bash -c "$(fetch_installer)" @ remove --purge
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "[cleanup] предупреждение: скрипт remove завершился с кодом $rc (xray мог быть не установлен)" >&2
  fi
}

_emit_xray_meta() {
  echo "###XRAY_META###"
  echo "private_key=${PRIVATE_KEY}"
  echo "public_key=${PUBLIC_KEY}"
  echo "###END_META###"
}
