#!/usr/bin/env bash
# VLESS XHTTP + TLS (Let's Encrypt) через Xray, без CDN.

set -euo pipefail

_xhttp_path_norm() {
  local p="${1:-/xhttp/}"
  [[ "$p" == /* ]] || p="/$p"
  [[ "$p" == */ ]] || p="$p/"
  printf '%s' "$p"
}

_write_xray_xhttp_config() {
  python3 - << 'PY'
import base64
import json
import os

port = int(os.environ["VPN_SERVER_PORT"])
api_port = int(os.environ.get("VPN_XRAY_API_PORT") or "10085")
fallback_uid = os.environ["VPN_VLESS_UUID"].strip()
inbound_tag = (os.environ.get("VPN_VLESS_INBOUND_TAG") or "vpn-vless-in").strip() or "vpn-vless-in"
xhttp_path = (os.environ.get("VPN_XHTTP_PATH") or "/xhttp/").strip() or "/xhttp/"
if not xhttp_path.startswith("/"):
    xhttp_path = "/" + xhttp_path
if not xhttp_path.endswith("/"):
    xhttp_path += "/"
cert_file = os.environ["VPN_TLS_CERT_FILE"].strip()
key_file = os.environ["VPN_TLS_KEY_FILE"].strip()

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
        clients.append({"id": u, "email": "u%d@vpn" % i, "level": 0})

for c in clients:
    c.pop("flow", None)
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
                "network": "xhttp",
                "security": "tls",
                "tlsSettings": {
                    "alpn": ["h3", "h2", "http/1.1"],
                    "certificates": [
                        {"certificateFile": cert_file, "keyFile": key_file}
                    ],
                },
                "xhttpSettings": {
                    "mode": "packet-up",
                    "path": xhttp_path,
                },
            },
        },
    ],
    "outbounds": [
        {"protocol": "freedom", "tag": "direct", "settings": {"domainStrategy": "UseIPv4"}},
    ],
}

cfg["inbounds"][0]["sniffing"] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
    "routeOnly": True,
}

print(json.dumps(cfg, indent=2, ensure_ascii=False))
PY
}

_vless_xhttp_apply_cascade_if_needed() {
  local CFG="${1:-${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}}"
  if [[ "${VPN_CASCADE_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ "${VPN_CASCADE_RU_DIRECT:-1}" != "0" ]]; then
    _xray_ensure_geo_dats || return 1
  fi
  _apply_xray_cascade_to_file "$CFG"
}

_vless_xhttp_install() {
  local domain xhttp_path
  domain="${VPN_TLS_DOMAIN:-}"
  xhttp_path=$(_xhttp_path_norm "${VPN_XHTTP_PATH:-/xhttp/}")
  export VPN_XHTTP_PATH="$xhttp_path"
  if [[ -z "$domain" ]]; then
    echo "[vless_xhttp] VPN_TLS_DOMAIN не задан" >&2
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[vless_xhttp] нужен python3" >&2
    exit 1
  fi

  _provision_preflight_packages || true

  echo "[vless_xhttp] установка Xray…"
  set +e
  bash -c "$(fetch_installer)" @ install
  local rc_install=$?
  set -e
  if [[ "$rc_install" -ne 0 ]]; then
    echo "[vless_xhttp] предупреждение: install-release.sh код $rc_install" >&2
  fi

  local XRAY_BIN
  XRAY_BIN=$(command -v xray || true)
  if [[ -z "$XRAY_BIN" ]]; then
    XRAY_BIN=/usr/local/bin/xray
  fi
  if [[ ! -x "$XRAY_BIN" ]]; then
    if ! _xray_install_direct_fallback; then
      echo "[vless_xhttp] бинарник xray не найден" >&2
      exit 1
    fi
    XRAY_BIN=/usr/local/bin/xray
  fi

  _tls_ensure_letsencrypt "$domain" || exit 1

  local CFG=/usr/local/etc/xray/config.json
  mkdir -p "$(dirname "$CFG")"
  echo "[vless_xhttp] запись $CFG (XHTTP+TLS, path=${xhttp_path})…"
  _write_xray_xhttp_config > "$CFG"
  _vless_xhttp_apply_cascade_if_needed || exit 1
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable xray 2>/dev/null || true
  fi
  _xray_test_config_and_restart "$CFG" "$XRAY_BIN" || exit 1
  _vps_net_sysctl_install || true
  echo "[vless_xhttp] готово: ${domain}:${VPN_SERVER_PORT} path=${xhttp_path}"
}

_vless_xhttp_sync_clients() {
  local domain="${VPN_TLS_DOMAIN:-}"
  if [[ -z "$domain" ]]; then
    echo "[vless_xhttp] sync: VPN_TLS_DOMAIN не задан" >&2
    exit 1
  fi
  export VPN_XHTTP_PATH="$(_xhttp_path_norm "${VPN_XHTTP_PATH:-/xhttp/}")"
  _tls_ensure_letsencrypt "$domain" || exit 1
  local CFG="${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}"
  echo "[vless_xhttp] sync_clients: запись $CFG…"
  _write_xray_xhttp_config > "$CFG"
  _vless_xhttp_apply_cascade_if_needed || exit 1
  local XBIN="${XRAY_BIN:-}"
  if [[ -z "$XBIN" || ! -x "$XBIN" ]]; then
    XBIN=$(command -v xray 2>/dev/null) || true
  fi
  if [[ -z "$XBIN" && -x /usr/local/bin/xray ]]; then
    XBIN=/usr/local/bin/xray
  fi
  _xray_test_config_and_restart "$CFG" "$XBIN" || exit 1
  echo "[vless_xhttp] sync_clients: перезапуск xray выполнен"
}
