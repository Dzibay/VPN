#!/usr/bin/env bash
# Удалённый хост: root. Режим: VPN_PROVISION_COMPONENT = all | xray | prometheus | cleanup
# all/xray: curl/wget, python3. prometheus: curl, systemctl. cleanup: curl/wget для uninstall xray.

set -euo pipefail

INSTALLER_URL="${VPN_XRAY_INSTALLER_URL:-https://github.com/XTLS/Xray-install/raw/main/install-release.sh}"
COMPONENT="${VPN_PROVISION_COMPONENT:-all}"

echo "[provision] component=${COMPONENT} host=$(hostname) id=${VPN_SERVER_ID:-?}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[provision] нужен root" >&2
  exit 1
fi

fetch_installer() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$INSTALLER_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$INSTALLER_URL"
  else
    echo "[provision] нужен curl или wget" >&2
    exit 1
  fi
}

# x25519: метки только в начале строки (без мусора [Info]).
_x25519_pick() {
  local out="$1"
  local label="$2"
  echo "$out" | grep -iE "^[[:space:]]*${label}[[:space:]]*:" | head -1 \
    | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]+$//'
}

_xray_install() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[xray] нужен python3 для записи config.json" >&2
    exit 1
  fi

  echo "[xray] установка (XTLS install-release.sh)…"
  bash -c "$(fetch_installer)" @ install

  XRAY_BIN=$(command -v xray || true)
  [[ -z "$XRAY_BIN" ]] && XRAY_BIN=/usr/local/bin/xray
  if [[ ! -x "$XRAY_BIN" ]]; then
    echo "[xray] не найден бинарник xray" >&2
    exit 1
  fi

  if [[ -n "${VPN_REALITY_PRIVATE_KEY:-}" ]]; then
    PRIVATE_KEY="$VPN_REALITY_PRIVATE_KEY"
    PUB_OUT=$($XRAY_BIN x25519 -i "$PRIVATE_KEY" 2>/dev/null || true)
    PUBLIC_KEY=$(_x25519_pick "$PUB_OUT" PublicKey)
    [[ -z "$PUBLIC_KEY" ]] && PUBLIC_KEY=$(_x25519_pick "$PUB_OUT" "Public[[:space:]]+Key")
    [[ -z "$PUBLIC_KEY" ]] && PUBLIC_KEY=$(_x25519_pick "$PUB_OUT" Password)
  else
    KP=$($XRAY_BIN x25519)
    PRIVATE_KEY=$(_x25519_pick "$KP" PrivateKey)
    PUBLIC_KEY=$(_x25519_pick "$KP" PublicKey)
    [[ -z "$PUBLIC_KEY" ]] && PUBLIC_KEY=$(_x25519_pick "$KP" "Public[[:space:]]+Key")
    [[ -z "$PUBLIC_KEY" ]] && PUBLIC_KEY=$(_x25519_pick "$KP" Password)
  fi

  if [[ -z "$PRIVATE_KEY" || -z "$PUBLIC_KEY" ]]; then
    echo "[xray] не удалось получить ключи REALITY (x25519)" >&2
    exit 1
  fi

  export VPN_REALITY_PRIVATE_KEY="$PRIVATE_KEY"

  CFG=/usr/local/etc/xray/config.json
  mkdir -p "$(dirname "$CFG")"

  echo "[xray] запись $CFG (VLESS REALITY → ${VPN_REALITY_DEST})…"
  python3 - << 'PY'
import json
import os

port = int(os.environ["VPN_SERVER_PORT"])
uid = os.environ["VPN_VLESS_UUID"]
dest = os.environ["VPN_REALITY_DEST"]
names = [x.strip() for x in os.environ["VPN_REALITY_SERVER_NAMES"].split(",") if x.strip()]
fp = os.environ.get("VPN_REALITY_FINGERPRINT", "chrome")
flow = os.environ.get("VPN_VLESS_FLOW", "xtls-rprx-vision")
short_id = os.environ["VPN_REALITY_SHORT_ID"].strip()
priv = os.environ["VPN_REALITY_PRIVATE_KEY"]

short_ids = ["", short_id] if short_id else [""]

cfg = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "listen": "0.0.0.0",
            "port": port,
            "protocol": "vless",
            "settings": {
                "clients": [{"id": uid, "flow": flow}],
                "decryption": "none",
            },
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
                },
            },
        }
    ],
    "outbounds": [
        {"protocol": "freedom", "tag": "direct"},
    ],
}

path = os.environ.get("VPN_XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY

  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable xray 2>/dev/null || true
    systemctl restart xray || true
  fi
}

_ne_install() {
  [[ "${VPN_INSTALL_NODE_EXPORTER:-1}" == "0" ]] && { echo "[node_exporter] отключено (VPN_INSTALL_NODE_EXPORTER=0)"; return 0; }
  [[ "${VPN_INSTALL_NODE_EXPORTER}" == "false" ]] && { echo "[node_exporter] отключено"; return 0; }
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[node_exporter] нет systemctl — пропуск" >&2
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "[node_exporter] нужен curl" >&2
    return 1
  fi

  local NE_VER="${VPN_NODE_EXPORTER_VERSION:-1.8.2}"
  local NE_PORT="${VPN_NODE_EXPORTER_PORT:-9100}"
  local NE_LH="${VPN_NODE_EXPORTER_LISTEN_HOST:-0.0.0.0}"
  local NE_BIN="/usr/local/bin/node_exporter"
  local NE_ARCH=""

  case "$(uname -m)" in
    x86_64|amd64) NE_ARCH=amd64 ;;
    aarch64|arm64) NE_ARCH=arm64 ;;
    *)
      echo "[node_exporter] архитектура $(uname -m) не поддерживается, пропуск" >&2
      return 0
      ;;
  esac

  echo "[node_exporter] v${NE_VER} (${NE_ARCH}), listen ${NE_LH}:${NE_PORT}…"
  local TMP
  TMP=$(mktemp -d)
  local URL="https://github.com/prometheus/node_exporter/releases/download/v${NE_VER}/node_exporter-${NE_VER}.linux-${NE_ARCH}.tar.gz"
  curl -fsSL "$URL" -o "$TMP/ne.tar.gz"
  tar xzf "$TMP/ne.tar.gz" -C "$TMP"
  if command -v install >/dev/null 2>&1; then
    install -m 755 "$TMP/node_exporter-${NE_VER}.linux-${NE_ARCH}/node_exporter" "$NE_BIN"
  else
    cp -f "$TMP/node_exporter-${NE_VER}.linux-${NE_ARCH}/node_exporter" "$NE_BIN"
    chmod 755 "$NE_BIN"
  fi
  rm -rf "$TMP"

  cat > /etc/systemd/system/node_exporter.service <<NEUNIT
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Restart=always
RestartSec=3
ExecStart=${NE_BIN} --web.listen-address=${NE_LH}:${NE_PORT}

[Install]
WantedBy=multi-user.target
NEUNIT

  systemctl daemon-reload
  systemctl enable node_exporter 2>/dev/null || true
  systemctl restart node_exporter || true
  echo "[node_exporter] сервис обновлён, ${NE_LH}:${NE_PORT}"
}

_cleanup() {
  echo "[cleanup] node_exporter: остановка и удаление…"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop node_exporter 2>/dev/null || true
    systemctl disable node_exporter 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/node_exporter.service
  rm -f /usr/local/bin/node_exporter
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
  fi

  echo "[cleanup] Xray: remove --purge (XTLS install-release.sh)…"
  set +e
  bash -c "$(fetch_installer)" @ remove --purge
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "[cleanup] предупреждение: скрипт remove завершился с кодом $rc (xray мог быть не установлен)" >&2
  fi
  echo "[cleanup] готово."
}

_emit_meta() {
  echo "###XRAY_META###"
  echo "private_key=${PRIVATE_KEY}"
  echo "public_key=${PUBLIC_KEY}"
  echo "###END_META###"
}

case "$COMPONENT" in
  cleanup)
    _cleanup
    ;;
  xray)
    _xray_install
    _emit_meta
    ;;
  prometheus|node_exporter)
    _ne_install
    ;;
  all|*)
    _xray_install
    _ne_install
    _emit_meta
    ;;
esac

echo "[provision] завершено (${COMPONENT})."
