#!/usr/bin/env bash
# Cloudflare WARP (WireGuard) для маршрутизации YouTube/Google на узлах с google_routing_mode=entry.

set -euo pipefail

_warp_dir() {
  echo "${VPN_WARP_DIR:-/usr/local/etc/xray/wgcf}"
}

_warp_profile_path() {
  echo "$(_warp_dir)/wgcf-profile.conf"
}

_warp_outbound_json_path() {
  echo "$(_warp_dir)/outbound.json"
}

_warp_wgcf_bin() {
  echo "${VPN_WGCF_BIN:-/usr/local/bin/wgcf}"
}

_warp_linux_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *)
      echo "[warp] архитектура $(uname -m) не поддерживается" >&2
      return 1
      ;;
  esac
}

_warp_install_wgcf() {
  local arch ver bin url
  arch=$(_warp_linux_arch) || return 1
  bin=$(_warp_wgcf_bin)
  if [[ -x "$bin" ]]; then
    return 0
  fi
  ver="${VPN_WGCF_VERSION:-2.2.22}"
  url="https://github.com/ViRb3/wgcf/releases/download/v${ver}/wgcf_${ver}_linux_${arch}"
  echo "[warp] загрузка wgcf v${ver} (${arch})…"
  curl -fsSL --connect-timeout 30 --max-time 180 "$url" -o "$bin"
  chmod 755 "$bin"
}

_warp_write_outbound_json() {
  local profile="$1"
  local out="$2"
  python3 - "$profile" "$out" <<'PY'
import json
import re
import sys

profile_path, out_path = sys.argv[1], sys.argv[2]
section = None
data: dict[str, dict[str, str]] = {}
with open(profile_path, encoding="utf-8") as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1).strip().lower()
            data.setdefault(section, {})
            continue
        if section and "=" in line:
            k, _, v = line.partition("=")
            data[section][k.strip().lower()] = v.strip()

iface = data.get("interface", {})
peer = data.get("peer", {})
secret = iface.get("privatekey", "").strip()
pub = peer.get("publickey", "").strip()
endpoint = peer.get("endpoint", "engage.cloudflareclient.com:2408").strip()
if not secret or not pub:
    raise SystemExit("wgcf-profile.conf: нет PrivateKey или PublicKey")

addrs = []
for part in iface.get("address", "").split(","):
    p = part.strip().split("/")[0].strip()
    if p:
        addrs.append(p)
if not addrs:
    addrs = ["172.16.0.2"]

host, _, port = endpoint.rpartition(":")
if not port:
    host, port = endpoint, "2408"

outbound = {
    "tag": "warp",
    "protocol": "wireguard",
    "settings": {
        "secretKey": secret,
        "address": addrs,
        "peers": [
            {
                "publicKey": pub,
                "endpoint": "%s:%s" % (host, port),
                "keepAlive": 25,
            }
        ],
        "mtu": 1280,
    },
}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(outbound, f, indent=2, ensure_ascii=False)
PY
}

_warp_ensure_credentials() {
  local dir profile outbound wgcf
  if [[ "${VPN_WARP_ENABLED:-1}" == "0" || "${VPN_WARP_ENABLED:-}" == "false" ]]; then
    echo "[warp] пропуск (VPN_WARP_ENABLED отключён)"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[warp] нужен python3" >&2
    return 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "[warp] нужен curl" >&2
    return 1
  fi

  dir=$(_warp_dir)
  profile=$(_warp_profile_path)
  outbound=$(_warp_outbound_json_path)
  mkdir -p "$dir"

  if [[ -f "$profile" && -f "$outbound" ]]; then
    echo "[warp] профиль уже есть: $profile"
    _warp_write_outbound_json "$profile" "$outbound"
    return 0
  fi

  _warp_install_wgcf || return 1
  wgcf=$(_warp_wgcf_bin)

  (
    cd "$dir"
    if [[ ! -f wgcf-account.toml ]]; then
      echo "[warp] регистрация аккаунта Cloudflare WARP…"
      if ! "$wgcf" register --accept-tos; then
        echo "[warp] wgcf register не удался" >&2
        exit 1
      fi
    fi
    echo "[warp] генерация WireGuard-профиля…"
    if ! "$wgcf" generate; then
      echo "[warp] wgcf generate не удался" >&2
      exit 1
    fi
  )

  if [[ ! -f "$profile" ]]; then
    echo "[warp] не найден $profile после wgcf generate" >&2
    return 1
  fi

  _warp_write_outbound_json "$profile" "$outbound"
  chmod 600 "$profile" "$outbound" 2>/dev/null || true
  echo "[warp] готово: outbound.json для Xray"
  return 0
}

_warp_ensure_if_youtube_entry() {
  local mode
  mode=$(echo "${VPN_GOOGLE_ROUTING_MODE:-exit}" | tr '[:upper:]' '[:lower:]')
  if [[ "$mode" != "entry" ]]; then
    return 0
  fi
  if _warp_ensure_credentials; then
    export VPN_WARP_OUTBOUND_JSON="$(_warp_outbound_json_path)"
    return 0
  fi
  echo "[warp] предупреждение: WARP недоступен — YouTube/Google пойдут direct (fallback)" >&2
  return 0
}

_warp_cleanup() {
  echo "[cleanup] warp: удаление wgcf…"
  rm -rf "$(_warp_dir)"
  rm -f "$(_warp_wgcf_bin)"
}
