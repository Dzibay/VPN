#!/usr/bin/env bash
# VLESS gRPC + TLS (Let's Encrypt) через Xray.

set -euo pipefail

_write_xray_grpc_config() {
  python3 - << 'PY'
import base64
import json
import os

port = int(os.environ["VPN_SERVER_PORT"])
api_port = int(os.environ.get("VPN_XRAY_API_PORT") or "10085")
fallback_uid = os.environ["VPN_VLESS_UUID"].strip()
inbound_tag = (os.environ.get("VPN_VLESS_INBOUND_TAG") or "vpn-vless-in").strip() or "vpn-vless-in"
domain = os.environ["VPN_TLS_DOMAIN"].strip()
service_name = os.environ["VPN_GRPC_SERVICE_NAME"].strip()
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
        clients.append(
            {
                "id": u,
                "email": "u%d@vpn" % i,
                "level": 0,
            }
        )

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
                "network": "grpc",
                "security": "tls",
                "tlsSettings": {
                    "alpn": ["h2"],
                    "certificates": [
                        {
                            "certificateFile": cert_file,
                            "keyFile": key_file,
                        }
                    ],
                },
                "grpcSettings": {
                    "serviceName": service_name,
                    "multiMode": False,
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

_tls_cert_paths() {
  local domain="$1"
  echo "/etc/letsencrypt/live/${domain}/fullchain.pem"
  echo "/etc/letsencrypt/live/${domain}/privkey.pem"
}

# Xray (часто User=nobody из install-release.sh) не читает /etc/letsencrypt — копируем в /usr/local/etc/xray/tls/.
_tls_xray_run_user() {
  local u
  u=$(systemctl show -p User --value xray 2>/dev/null || true)
  u="${u:-}"
  if [[ -z "$u" || "$u" == "root" ]]; then
    if [[ -f /etc/systemd/system/xray.service ]]; then
      u=$(grep -E '^User=' /etc/systemd/system/xray.service 2>/dev/null | head -1 | cut -d= -f2- || true)
    fi
  fi
  echo "${u:-nobody}"
}

_tls_publish_for_xray() {
  local domain="$1"
  local src_cert src_key dest_dir xray_user
  src_cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
  src_key="/etc/letsencrypt/live/${domain}/privkey.pem"
  if [[ ! -s "$src_cert" || ! -s "$src_key" ]]; then
    echo "[vless_grpc] нет LE-сертификата для ${domain}" >&2
    return 1
  fi
  dest_dir="/usr/local/etc/xray/tls/${domain}"
  mkdir -p "$dest_dir"
  cp -L "$src_cert" "${dest_dir}/fullchain.pem"
  cp -L "$src_key" "${dest_dir}/privkey.pem"
  xray_user=$(_tls_xray_run_user)
  chown -R "${xray_user}:${xray_user}" "$dest_dir"
  chmod 755 "$dest_dir"
  chmod 644 "${dest_dir}/fullchain.pem"
  chmod 640 "${dest_dir}/privkey.pem"
  export VPN_TLS_CERT_FILE="${dest_dir}/fullchain.pem"
  export VPN_TLS_KEY_FILE="${dest_dir}/privkey.pem"
  echo "[vless_grpc] TLS для xray (${xray_user}): ${VPN_TLS_CERT_FILE}"
}

_tls_install_certbot() {
  if command -v certbot >/dev/null 2>&1; then
    return 0
  fi
  echo "[vless_grpc] установка certbot…"
  _provision_preflight_packages || true
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq 2>&1 | tail -20 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends certbot 2>&1 | tail -40
  elif command -v dnf >/dev/null 2>&1; then
    dnf -y install certbot 2>&1 | tail -40
  elif command -v yum >/dev/null 2>&1; then
    yum -y install certbot 2>&1 | tail -40
  elif command -v zypper >/dev/null 2>&1; then
    zypper install -y certbot 2>&1 | tail -40
  fi
  command -v certbot >/dev/null 2>&1
}

_tls_ensure_letsencrypt() {
  local domain="$1"
  local email="${VPN_TLS_CERTBOT_EMAIL:-admin@${domain}}"
  local cert_file key_file
  cert_file="/etc/letsencrypt/live/${domain}/fullchain.pem"
  key_file="/etc/letsencrypt/live/${domain}/privkey.pem"

  if ! _tls_install_certbot; then
    echo "[vless_grpc] certbot не установлен" >&2
    return 1
  fi

  if [[ -s "$cert_file" && -s "$key_file" ]]; then
    echo "[vless_grpc] TLS-сертификат уже есть: $cert_file"
    certbot renew --quiet --no-self-upgrade 2>/dev/null || true
    _tls_publish_for_xray "$domain" || return 1
    return 0
  fi

  echo "[vless_grpc] выпуск Let's Encrypt для ${domain} (порт 80 должен быть свободен)…"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop xray 2>/dev/null || true
  fi
  set +e
  certbot certonly --standalone \
    --preferred-challenges http \
    --http-01-port 80 \
    -d "$domain" \
    --non-interactive --agree-tos \
    -m "$email"
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "[vless_grpc] certbot завершился с кодом $rc" >&2
    echo "[vless_grpc] Проверьте: A-запись ${domain} → IP узла, порт 80 открыт снаружи." >&2
    return 1
  fi
  if [[ ! -s "$cert_file" || ! -s "$key_file" ]]; then
    echo "[vless_grpc] certbot не создал файлы сертификата" >&2
    return 1
  fi
  _tls_publish_for_xray "$domain" || return 1
  echo "[vless_grpc] сертификат получен"
}

_vless_grpc_install() {
  local domain service_name
  domain="${VPN_TLS_DOMAIN:-}"
  service_name="${VPN_GRPC_SERVICE_NAME:-grpc}"
  if [[ -z "$domain" ]]; then
    echo "[vless_grpc] VPN_TLS_DOMAIN не задан" >&2
    exit 1
  fi
  if [[ -z "$service_name" ]]; then
    echo "[vless_grpc] VPN_GRPC_SERVICE_NAME не задан" >&2
    exit 1
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "[vless_grpc] нужен python3" >&2
    exit 1
  fi

  _provision_preflight_packages || true

  echo "[vless_grpc] установка Xray…"
  set +e
  bash -c "$(fetch_installer)" @ install
  local rc_install=$?
  set -e
  if [[ "$rc_install" -ne 0 ]]; then
    echo "[vless_grpc] предупреждение: install-release.sh код $rc_install" >&2
  fi

  local XRAY_BIN
  XRAY_BIN=$(command -v xray || true)
  if [[ -z "$XRAY_BIN" ]]; then
    XRAY_BIN=/usr/local/bin/xray
  fi
  if [[ ! -x "$XRAY_BIN" ]]; then
    if ! _xray_install_direct_fallback; then
      echo "[vless_grpc] бинарник xray не найден" >&2
      exit 1
    fi
    XRAY_BIN=/usr/local/bin/xray
  fi

  _tls_ensure_letsencrypt "$domain" || exit 1

  local CFG=/usr/local/etc/xray/config.json
  mkdir -p "$(dirname "$CFG")"
  echo "[vless_grpc] запись $CFG (gRPC+TLS, service=${service_name})…"
  _write_xray_grpc_config > "$CFG"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable xray 2>/dev/null || true
  fi
  _xray_test_config_and_restart "$CFG" "$XRAY_BIN" || exit 1
  _vps_net_sysctl_install || true
  echo "[vless_grpc] готово: ${domain}:${VPN_SERVER_PORT} serviceName=${service_name}"
}

_vless_grpc_sync_clients() {
  local domain="${VPN_TLS_DOMAIN:-}"
  if [[ -z "$domain" ]]; then
    echo "[vless_grpc] sync: VPN_TLS_DOMAIN не задан" >&2
    exit 1
  fi
  _tls_ensure_letsencrypt "$domain" || exit 1
  local CFG="${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}"
  echo "[vless_grpc] sync_clients: запись $CFG…"
  _write_xray_grpc_config > "$CFG"
  local XBIN="${XRAY_BIN:-}"
  if [[ -z "$XBIN" || ! -x "$XBIN" ]]; then
    XBIN=$(command -v xray 2>/dev/null) || true
  fi
  if [[ -z "$XBIN" && -x /usr/local/bin/xray ]]; then
    XBIN=/usr/local/bin/xray
  fi
  _xray_test_config_and_restart "$CFG" "$XBIN" || exit 1
  echo "[vless_grpc] sync_clients: перезапуск xray выполнен"
}
