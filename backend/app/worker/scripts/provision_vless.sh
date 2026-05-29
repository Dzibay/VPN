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
# routeOnly=True: домен из sniff только для routing (RU/не-RU, Gemini); целевой адрес пакета не подменяется —
# меньше поломок push/банков при обращении по IP или чувствительных TLS. Каскаду нужен стабильный match по домену.
cfg["inbounds"][0]["sniffing"] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
    "routeOnly": True,
}

google_mode = (os.environ.get("VPN_GOOGLE_ROUTING_MODE") or "exit").strip().lower()
if google_mode not in ("exit", "entry"):
    google_mode = "exit"
google_via_exit = google_mode == "exit"

gemini_domains = [
    "domain:gemini.google.com",
    "domain:aistudio.google.com",
    "domain:clients6.google.com",
    "domain:generativelanguage.googleapis.com",
    "domain:alkalimining-pa.googleapis.com",
    "domain:proactivebackend-pa.googleapis.com",
]
_google_geosites = ("geosite:youtube", "geosite:google")
gemini_tag = "egress-cascade" if cascade else "direct"
google_rules = []
if google_via_exit:
    google_rules = [
        {"type": "field", "outboundTag": gemini_tag, "domain": gemini_domains},
        {"type": "field", "outboundTag": gemini_tag, "ip": ["geoip:google"]},
    ]
elif not cascade:
    google_rules = [
        {
            "type": "field",
            "outboundTag": "direct",
            "domain": [*_google_geosites, *gemini_domains],
        },
    ]

if not cascade:
    cfg["outbounds"].append({"protocol": "blackhole", "tag": "block"})
    cfg["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": google_rules,
    }

path = os.environ.get("VPN_XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY
  if [[ "${VPN_CASCADE_ENABLED:-0}" == "1" ]]; then
    _apply_xray_cascade_to_file "${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}"
  fi
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

_xray_linux_machine_suffix() {
  case "$(uname -m)" in
    x86_64|amd64) echo "64" ;;
    aarch64|arm64) echo "arm64-v8a" ;;
    *)
      echo "[xray] fallback: архитектура $(uname -m) не поддерживается" >&2
      return 1
      ;;
  esac
}

_xray_fetch_latest_version() {
  local tmp v
  tmp=$(mktemp)
  if ! curl -fsSL --connect-timeout 30 --max-time 120 \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/XTLS/Xray-core/releases/latest" -o "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  v=$(grep -m1 '"tag_name"' "$tmp" | sed -E 's/.*"([^"]+)".*/\1/' || true)
  rm -f "$tmp"
  [[ -n "$v" ]] || return 1
  echo "${v#v}"
}

_xray_unzip_to_dir() {
  local zip="$1" dest="$2"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q -o "$zip" -d "$dest"
    return $?
  fi
  python3 - "$zip" "$dest" <<'PY'
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY
}

_xray_ensure_systemd_unit() {
  if [[ -f /etc/systemd/system/xray.service ]]; then
    return 0
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  mkdir -p /usr/local/etc/xray /usr/local/share/xray
  if [[ ! -f /usr/local/etc/xray/config.json ]]; then
    echo '{}' > /usr/local/etc/xray/config.json
  fi
  cat > /etc/systemd/system/xray.service <<'UNIT'
[Unit]
Description=Xray Service
Documentation=https://github.com/xtls
After=network-online.target nss-lookup.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload 2>/dev/null || true
}

_xray_install_direct_fallback() {
  echo "[xray] fallback: прямая установка бинарника с GitHub…"
  local machine ver tmp zip url
  machine=$(_xray_linux_machine_suffix) || return 1
  ver="${VPN_XRAY_INSTALL_VERSION:-}"
  if [[ -z "$ver" ]]; then
    ver=$(_xray_fetch_latest_version) || {
      echo "[xray] fallback: не удалось получить версию (GitHub API)" >&2
      return 1
    }
  fi
  ver="${ver#v}"
  if ! command -v curl >/dev/null 2>&1; then
    echo "[xray] fallback: нужен curl" >&2
    return 1
  fi
  tmp=$(mktemp -d)
  zip="$tmp/Xray-linux-${machine}.zip"
  url="https://github.com/XTLS/Xray-core/releases/download/v${ver}/Xray-linux-${machine}.zip"
  echo "[xray] fallback: $url"
  if ! curl -fSL --connect-timeout 30 --max-time 300 --retry 3 --retry-delay 8 \
    -o "$zip" "$url"; then
    echo "[xray] fallback: загрузка не удалась" >&2
    rm -rf "$tmp"
    return 1
  fi
  if ! _xray_unzip_to_dir "$zip" "$tmp"; then
    echo "[xray] fallback: распаковка zip не удалась" >&2
    rm -rf "$tmp"
    return 1
  fi
  if [[ ! -f "$tmp/xray" ]]; then
    echo "[xray] fallback: в архиве нет xray" >&2
    rm -rf "$tmp"
    return 1
  fi
  install -m 755 "$tmp/xray" /usr/local/bin/xray
  mkdir -p /usr/local/share/xray
  [[ -f "$tmp/geoip.dat" ]] && install -m 644 "$tmp/geoip.dat" /usr/local/share/xray/geoip.dat
  [[ -f "$tmp/geosite.dat" ]] && install -m 644 "$tmp/geosite.dat" /usr/local/share/xray/geosite.dat
  rm -rf "$tmp"
  _xray_ensure_systemd_unit || true
  echo "[xray] fallback: $(/usr/local/bin/xray -version 2>/dev/null | head -1 || echo ok)"
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

  _provision_preflight_packages || true

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
    echo "[xray] бинарник не найден после install-release.sh, пробуем fallback…" >&2
    if ! _xray_install_direct_fallback; then
      echo "[xray] не найден бинарник xray" >&2
      echo "[xray] Частые причины: apt не ставит unzip (зеркала ОС), или нет HTTPS до GitHub." >&2
      echo "[xray] На узле: apt-get update && apt-get install -y unzip curl" >&2
      echo "[xray] Проверка: curl -vI https://github.com  и  curl -vI https://github.com/XTLS/Xray-core/releases" >&2
      echo "[xray] Обход: HTTPS_PROXY, другое зеркало apt, или xray вручную в /usr/local/bin/xray и повтор provision." >&2
      exit 1
    fi
    XRAY_BIN=/usr/local/bin/xray
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
