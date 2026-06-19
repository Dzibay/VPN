#!/usr/bin/env bash
# VLESS XHTTP через VK Cloud CDN: TLS/decoy/nginx на origin, Xray локально на 4443.

set -euo pipefail

_vkcdn_xhttp_path() {
  local p="${1:-/uploadfiles/}"
  [[ "$p" == /* ]] || p="/$p"
  [[ "$p" == */ ]] || p="$p/"
  printf '%s' "$p"
}

_write_xray_vkcdn_xhttp_config() {
  python3 - << 'PY'
import base64
import json
import os

port = int(os.environ.get("VPN_XHTTP_LOCAL_PORT") or "4443")
api_port = int(os.environ.get("VPN_XRAY_API_PORT") or "10085")
fallback_uid = os.environ["VPN_VLESS_UUID"].strip()
inbound_tag = (os.environ.get("VPN_VLESS_INBOUND_TAG") or "VKCDN").strip() or "VKCDN"
xhttp_path = (os.environ.get("VPN_XHTTP_PATH") or "/uploadfiles/").strip() or "/uploadfiles/"
if not xhttp_path.startswith("/"):
    xhttp_path = "/" + xhttp_path
if not xhttp_path.endswith("/"):
    xhttp_path += "/"

b64 = (os.environ.get("VPN_VLESS_CLIENTS_B64") or "").strip()
clients = []
if b64:
    try:
        clients = json.loads(base64.b64decode(b64).decode("utf-8"))
    except Exception:
        clients = []
if not clients:
    raw = (os.environ.get("VPN_VLESS_CLIENT_UUIDS") or "").strip()
    uuids = [x.strip() for x in raw.split(",") if x.strip()] if raw else [fallback_uid]
    seen = set()
    clients = []
    for i, u in enumerate(uuids):
        if not u or u in seen:
            continue
        seen.add(u)
        clients.append({"id": u, "email": "u%d@vpn" % i, "level": 0})
if not clients and fallback_uid:
    clients.append({"id": fallback_uid, "email": "u0@vpn", "level": 0})

for c in clients:
    c.pop("flow", None)
    c.setdefault("level", 0)
    c.setdefault("email", "u0@vpn")

cfg = {
    "log": {"loglevel": "warning"},
    "dns": {
        "servers": [{"address": "8.8.8.8", "skipFallback": False}],
        "queryStrategy": "UseIPv4",
    },
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
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            "streamSettings": {
                "network": "xhttp",
                "security": "none",
                "xhttpSettings": {
                    "mode": "packet-up",
                    "path": xhttp_path,
                    "extra": {
                        "xPaddingKey": "_dc",
                        "xPaddingHeader": "X-Cache",
                        "xPaddingMethod": "tokenish",
                        "uplinkHTTPMethod": "GET",
                        "xPaddingObfsMode": True,
                        "xPaddingPlacement": "queryInHeader",
                    },
                },
            },
        },
    ],
    "outbounds": [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ],
    "routing": {
        "rules": [
            {"ip": ["geoip:private"], "type": "field", "outboundTag": "block"},
            {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
        ],
        "domainStrategy": "IPIfNonMatch",
    },
}

print(json.dumps(cfg, indent=2, ensure_ascii=False))
PY
}

_vkcdn_ensure_tls_cert() {
  local origin="$1"
  local email="${VPN_TLS_CERTBOT_EMAIL:-admin@${origin}}"
  local le_cert="/etc/letsencrypt/live/${origin}/fullchain.pem"
  local le_key="/etc/letsencrypt/live/${origin}/privkey.pem"
  local fallback_dir="/etc/ssl/vpn-vkcdn-xhttp/${origin}"
  local fallback_cert="${fallback_dir}/fullchain.pem"
  local fallback_key="${fallback_dir}/privkey.pem"

  if [[ -s "$le_cert" && -s "$le_key" ]]; then
    export VPN_VKCDN_SSL_CERT="$le_cert"
    export VPN_VKCDN_SSL_KEY="$le_key"
    echo "[vkcdn_xhttp] TLS: найден Let's Encrypt сертификат для ${origin}"
    return 0
  fi

  if ! command -v certbot >/dev/null 2>&1; then
    echo "[vkcdn_xhttp] установка certbot…"
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq certbot 2>/dev/null || true
  fi

  if command -v certbot >/dev/null 2>&1; then
    echo "[vkcdn_xhttp] пробую выпустить Let's Encrypt для ${origin}…"
    if command -v systemctl >/dev/null 2>&1; then
      systemctl stop nginx 2>/dev/null || true
      systemctl stop xray 2>/dev/null || true
    fi
    set +e
    certbot certonly --standalone \
      --preferred-challenges http \
      --http-01-port 80 \
      -d "$origin" \
      --non-interactive --agree-tos \
      -m "$email"
    local rc=$?
    set -e
    if [[ "$rc" -eq 0 && -s "$le_cert" && -s "$le_key" ]]; then
      export VPN_VKCDN_SSL_CERT="$le_cert"
      export VPN_VKCDN_SSL_KEY="$le_key"
      echo "[vkcdn_xhttp] TLS: Let's Encrypt сертификат получен"
      return 0
    fi
    echo "[vkcdn_xhttp] предупреждение: Let's Encrypt не выпущен (код ${rc}); создаю self-signed fallback" >&2
    echo "[vkcdn_xhttp] проверьте DNS: ${origin} должен резолвиться в IP этого VPS до настройки VK CDN" >&2
  else
    echo "[vkcdn_xhttp] предупреждение: certbot недоступен; создаю self-signed fallback" >&2
  fi

  if ! command -v openssl >/dev/null 2>&1; then
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq openssl 2>/dev/null || true
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "[vkcdn_xhttp] openssl не найден — не могу создать self-signed сертификат" >&2
    return 1
  fi

  mkdir -p "$fallback_dir"
  if [[ ! -s "$fallback_cert" || ! -s "$fallback_key" ]]; then
    local cn="${origin:0:64}"
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout "$fallback_key" \
      -out "$fallback_cert" \
      -subj "/CN=${cn}" >/dev/null 2>&1
    chmod 600 "$fallback_key" 2>/dev/null || true
  fi
  export VPN_VKCDN_SSL_CERT="$fallback_cert"
  export VPN_VKCDN_SSL_KEY="$fallback_key"
  echo "[vkcdn_xhttp] TLS: используется self-signed fallback (${fallback_cert})"
}

_vkcdn_install_nginx() {
  local origin="$1"
  local xhttp_path="$2"
  local xray_port="${VPN_XHTTP_LOCAL_PORT:-4443}"
  local cert_file="${VPN_VKCDN_SSL_CERT:-/etc/letsencrypt/live/${origin}/fullchain.pem}"
  local key_file="${VPN_VKCDN_SSL_KEY:-/etc/letsencrypt/live/${origin}/privkey.pem}"

  if ! command -v nginx >/dev/null 2>&1; then
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq nginx 2>/dev/null || {
      echo "[vkcdn_xhttp] не удалось установить nginx" >&2
      return 1
    }
  fi

  mkdir -p /var/www/decoy
  if [[ ! -s /var/www/decoy/index.html ]]; then
    GHOST_DECOY="${VPN_DECOY_TEMPLATE:-vkcloud}" \
      GHOST_DECOY_DIR=/var/www/decoy \
      bash <(curl -sL https://info.ghostos.space/spectral/core/sc-decoy.sh) || {
        echo "[vkcdn_xhttp] предупреждение: sc-decoy.sh не выполнился, создаю минимальную заглушку" >&2
        cat > /var/www/decoy/index.html <<'HTML'
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>VK Cloud</title></head><body><h1>VK Cloud</h1></body></html>
HTML
      }
  fi
  chown -R www-data:www-data /var/www/decoy 2>/dev/null || true

  local conf
  if [[ -d /etc/nginx/sites-available ]]; then
    conf="/etc/nginx/sites-available/vpn-vkcdn-xhttp.conf"
    rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/vpn-vkcdn-xhttp.conf
  else
    conf="/etc/nginx/conf.d/vpn-vkcdn-xhttp.conf"
    rm -f /etc/nginx/conf.d/default.conf
  fi

  cat > "$conf" <<NGINXEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${origin};

    location /.well-known/acme-challenge/ {
        root /var/www/decoy;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${origin};

    ssl_certificate     ${cert_file};
    ssl_certificate_key ${key_file};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    server_tokens off;
    root /var/www/decoy;
    index index.html;

    client_max_body_size 0;
    client_body_timeout 3600s;
    client_header_timeout 3600s;
    client_header_buffer_size 16k;
    large_client_header_buffers 8 32k;

    access_log /var/log/nginx/xhttp_access.log;
    error_log /var/log/nginx/error.log warn;

    location = /health {
        default_type application/json;
        add_header Cache-Control "no-store" always;
        return 200 '{"status":"ok"}';
    }

    location ${xhttp_path} {
        proxy_pass http://127.0.0.1:${xray_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_connect_timeout 60s;
    }

    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files \$uri \$uri/ =404;
    }
}
NGINXEOF

  if [[ -d /etc/nginx/sites-enabled ]]; then
    ln -sf "$conf" /etc/nginx/sites-enabled/vpn-vkcdn-xhttp.conf
  fi
  nginx -t || return 1
  systemctl enable nginx 2>/dev/null || true
  systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
}

_vless_vkcdn_xhttp_install() {
  local origin="${VPN_ORIGIN_DOMAIN:-}"
  local cdn="${VPN_CDN_DOMAIN:-}"
  local xhttp_path
  xhttp_path=$(_vkcdn_xhttp_path "${VPN_XHTTP_PATH:-/uploadfiles/}")
  export VPN_XHTTP_PATH="$xhttp_path"
  export VPN_XHTTP_LOCAL_PORT="${VPN_XHTTP_LOCAL_PORT:-4443}"

  if [[ -z "$origin" || -z "$cdn" ]]; then
    echo "[vkcdn_xhttp] VPN_ORIGIN_DOMAIN и VPN_CDN_DOMAIN обязательны" >&2
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[vkcdn_xhttp] нужен python3" >&2
    exit 1
  fi

  _provision_preflight_packages || true

  echo "[vkcdn_xhttp] установка Xray…"
  set +e
  bash -c "$(fetch_installer)" @ install
  local rc_install=$?
  set -e
  if [[ "$rc_install" -ne 0 ]]; then
    echo "[vkcdn_xhttp] предупреждение: install-release.sh код $rc_install" >&2
  fi

  local XRAY_BIN
  XRAY_BIN=$(command -v xray || true)
  if [[ -z "$XRAY_BIN" ]]; then
    XRAY_BIN=/usr/local/bin/xray
  fi
  if [[ ! -x "$XRAY_BIN" ]]; then
    if ! _xray_install_direct_fallback; then
      echo "[vkcdn_xhttp] бинарник xray не найден" >&2
      exit 1
    fi
    XRAY_BIN=/usr/local/bin/xray
  fi

  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop nginx 2>/dev/null || true
  fi
  _vkcdn_ensure_tls_cert "$origin" || exit 1
  _vkcdn_install_nginx "$origin" "$xhttp_path" || exit 1

  local CFG=/usr/local/etc/xray/config.json
  mkdir -p "$(dirname "$CFG")"
  echo "[vkcdn_xhttp] запись $CFG (XHTTP packet-up, path=${xhttp_path})…"
  _write_xray_vkcdn_xhttp_config > "$CFG"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable xray 2>/dev/null || true
  fi
  _xray_test_config_and_restart "$CFG" "$XRAY_BIN" || exit 1
  _vps_net_sysctl_install || true
  systemctl reload nginx 2>/dev/null || true
  echo "[vkcdn_xhttp] готово: origin=${origin} cdn=${cdn}:443 path=${xhttp_path} local_xray=${VPN_XHTTP_LOCAL_PORT}"
}

_vless_vkcdn_xhttp_sync_clients() {
  local origin="${VPN_ORIGIN_DOMAIN:-}"
  local xhttp_path
  xhttp_path=$(_vkcdn_xhttp_path "${VPN_XHTTP_PATH:-/uploadfiles/}")
  export VPN_XHTTP_PATH="$xhttp_path"
  export VPN_XHTTP_LOCAL_PORT="${VPN_XHTTP_LOCAL_PORT:-4443}"
  if [[ -z "$origin" ]]; then
    echo "[vkcdn_xhttp] sync: VPN_ORIGIN_DOMAIN не задан" >&2
    exit 1
  fi
  local CFG="${VPN_XRAY_CONFIG_PATH:-/usr/local/etc/xray/config.json}"
  echo "[vkcdn_xhttp] sync_clients: запись $CFG…"
  _write_xray_vkcdn_xhttp_config > "$CFG"
  local XBIN="${XRAY_BIN:-}"
  if [[ -z "$XBIN" || ! -x "$XBIN" ]]; then
    XBIN=$(command -v xray 2>/dev/null) || true
  fi
  if [[ -z "$XBIN" && -x /usr/local/bin/xray ]]; then
    XBIN=/usr/local/bin/xray
  fi
  _xray_test_config_and_restart "$CFG" "$XBIN" || exit 1
  echo "[vkcdn_xhttp] sync_clients: перезапуск xray выполнен"
}
