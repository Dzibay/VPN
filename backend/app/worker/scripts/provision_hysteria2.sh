#!/usr/bin/env bash
# Установка Hysteria2 через официальный installer + systemd service.

set -euo pipefail

_hysteria2_install() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[hysteria2] нужен systemctl" >&2
    return 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "[hysteria2] нужен curl" >&2
    return 1
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "[hysteria2] нужен openssl" >&2
    return 1
  fi

  echo "[hysteria2] установка официальным installer (get.hy2.sh)…"
  bash -c "$(curl -fsSL https://get.hy2.sh/)"

  local bin cfg_dir cfg_file cert_file key_file domain pass port masquerade
  bin="$(command -v hysteria 2>/dev/null || true)"
  if [[ -z "$bin" && -x /usr/local/bin/hysteria ]]; then
    bin="/usr/local/bin/hysteria"
  fi
  if [[ -z "$bin" || ! -x "$bin" ]]; then
    echo "[hysteria2] бинарник hysteria не найден после установки" >&2
    return 1
  fi

  domain="${VPN_HYSTERIA2_DOMAIN:-localhost}"
  pass="${VPN_HYSTERIA2_PASSWORD:-changeme}"
  port="${VPN_SERVER_PORT:-443}"
  masquerade="${VPN_HYSTERIA2_MASQUERADE:-https://www.bing.com}"
  cfg_dir="/etc/hysteria"
  cfg_file="${cfg_dir}/config.yaml"
  cert_file="${cfg_dir}/server.crt"
  key_file="${cfg_dir}/server.key"

  install -d -m 700 "$cfg_dir"
  if [[ ! -s "$cert_file" || ! -s "$key_file" ]]; then
    openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
      -keyout "$key_file" \
      -out "$cert_file" \
      -subj "/CN=${domain}" >/dev/null 2>&1
    chmod 600 "$key_file"
    chmod 644 "$cert_file"
  fi

  cat > "$cfg_file" <<EOF
listen: :${port}

tls:
  cert: ${cert_file}
  key: ${key_file}

auth:
  type: password
  password: ${pass}

masquerade:
  type: proxy
  proxy:
    url: ${masquerade}
    rewriteHost: true
EOF
  chmod 600 "$cfg_file"

  cat > /etc/systemd/system/hysteria-server.service <<UNIT
[Unit]
Description=Hysteria2 Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${bin} server -c ${cfg_file}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

  systemctl daemon-reload
  systemctl enable hysteria-server 2>/dev/null || true
  systemctl restart hysteria-server
  echo "[hysteria2] установлен на UDP/TCP порту ${port} (domain=${domain})"
}

_hysteria2_cleanup() {
  echo "[cleanup] Hysteria2: остановка и удаление…"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop hysteria-server 2>/dev/null || true
    systemctl disable hysteria-server 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/hysteria-server.service
  rm -rf /etc/hysteria
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
  fi
}
