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
  else
    echo "[warp] предупреждение: WARP недоступен — YouTube/Google пойдут direct (fallback)" >&2
  fi
  _warp_install_monitor || true
  return 0
}

_warp_textfile_dir() {
  echo "${VPN_NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile}"
}

_warp_install_monitor() {
  if [[ "${VPN_WARP_MONITOR_ENABLED:-1}" == "0" || "${VPN_WARP_MONITOR_ENABLED:-}" == "false" ]]; then
    echo "[warp] мониторинг отключён (VPN_WARP_MONITOR_ENABLED=0)"
    return 0
  fi
  _node_exporter_ensure_textfile_collector || true
  install -d -m 755 /usr/local/sbin 2>/dev/null || mkdir -p /usr/local/sbin

  cat > /usr/local/sbin/vpn-warp-check.sh <<'EOS'
#!/usr/bin/env bash
# Метрики WARP для Prometheus textfile collector (node_exporter).
set -uo pipefail

WARP_DIR="${VPN_WARP_DIR:-/usr/local/etc/xray/wgcf}"
TEXTFILE_DIR="${VPN_NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile}"
OUT="${TEXTFILE_DIR}/warp.prom"
TMP="${OUT}.$$"
PROBE_URL="${VPN_WARP_PROBE_URL:-https://www.youtube.com/generate_204}"
ENDPOINT_HOST="${VPN_WARP_ENDPOINT_HOST:-engage.cloudflareclient.com}"
ENDPOINT_PORT="${VPN_WARP_ENDPOINT_PORT:-2408}"

mkdir -p "$TEXTFILE_DIR"

python3 - "$WARP_DIR" "$PROBE_URL" "$ENDPOINT_HOST" "$ENDPOINT_PORT" "$TMP" <<'PY'
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request

warp_dir, probe_url, ep_host, ep_port, out_path = sys.argv[1:6]

def read_toml(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                data[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return data

profile_ok = 0
outbound_ok = 0
account_ok = 0
endpoint_ok = 0
cf_api_ok = 0
warp_plus = 0
quota_bytes = -1.0
premium_data_bytes = -1.0
probe_ok = 0
probe_ms = -1.0
account_type = "unknown"
license = "unknown"
cf_error = ""

profile = f"{warp_dir}/wgcf-profile.conf"
outbound = f"{warp_dir}/outbound.json"
account_toml = f"{warp_dir}/wgcf-account.toml"

if __import__("os").path.isfile(profile):
    profile_ok = 1
if __import__("os").path.isfile(outbound):
    outbound_ok = 1
if __import__("os").path.isfile(account_toml):
    account_ok = 1

t0 = time.perf_counter()
try:
    with socket.create_connection((ep_host, int(ep_port)), timeout=4.0):
        endpoint_ok = 1
except OSError:
    endpoint_ok = 0

t1 = time.perf_counter()
try:
    req = urllib.request.Request(
        probe_url,
        headers={"User-Agent": "vpn-warp-check/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=8.0) as resp:
        probe_ok = 1 if 200 <= int(resp.status) < 400 else 0
except (urllib.error.URLError, OSError, ValueError):
    probe_ok = 0
probe_ms = round((time.perf_counter() - t1) * 1000.0, 2)

acc = read_toml(account_toml)
device_id = acc.get("device_id", "").strip()
access_token = acc.get("access_token", "").strip()
if device_id and access_token:
    url = f"https://api.cloudflareclient.com/v0/reg/{device_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "vpn-warp-check/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(body) if body.strip() else {}
        cf_api_ok = 1
        account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
        account_type = str(account.get("account_type") or payload.get("account_type") or "unknown")
        license = str(account.get("license") or payload.get("license") or "unknown")
        if account.get("warp_plus") is True or payload.get("warp_plus") is True:
            warp_plus = 1
        for key in ("premium_data_bytes", "premium_data", "used_bytes"):
            val = account.get(key, payload.get(key))
            if isinstance(val, (int, float)) and val >= 0:
                premium_data_bytes = float(val)
                break
        for key in ("quota_bytes", "premium_data_limit_bytes", "limit_bytes"):
            val = account.get(key, payload.get(key))
            if isinstance(val, (int, float)) and val >= 0:
                quota_bytes = float(val)
                break
    except Exception as e:
        cf_error = str(e)[:120]

now = int(time.time())
lines = [
    "# HELP vpn_warp_profile_ok wgcf WireGuard profile present on disk",
    "# TYPE vpn_warp_profile_ok gauge",
    f"vpn_warp_profile_ok {profile_ok}",
    "# HELP vpn_warp_outbound_ok Xray warp outbound.json present",
    "# TYPE vpn_warp_outbound_ok gauge",
    f"vpn_warp_outbound_ok {outbound_ok}",
    "# HELP vpn_warp_account_ok wgcf-account.toml present",
    "# TYPE vpn_warp_account_ok gauge",
    f"vpn_warp_account_ok {account_ok}",
    "# HELP vpn_warp_endpoint_reachable Cloudflare WARP WireGuard endpoint TCP reachable",
    "# TYPE vpn_warp_endpoint_reachable gauge",
    f"vpn_warp_endpoint_reachable {endpoint_ok}",
    "# HELP vpn_warp_cf_api_ok Cloudflare WARP registration API responded",
    "# TYPE vpn_warp_cf_api_ok gauge",
    f"vpn_warp_cf_api_ok {cf_api_ok}",
    "# HELP vpn_warp_warp_plus WARP+ / unlimited account flag from Cloudflare API",
    "# TYPE vpn_warp_warp_plus gauge",
    f"vpn_warp_warp_plus {warp_plus}",
    "# HELP vpn_warp_probe_ok HTTP probe to YouTube generate_204 from server",
    "# TYPE vpn_warp_probe_ok gauge",
    f"vpn_warp_probe_ok {probe_ok}",
    "# HELP vpn_warp_probe_latency_ms HTTP probe latency milliseconds",
    "# TYPE vpn_warp_probe_latency_ms gauge",
    f"vpn_warp_probe_latency_ms {probe_ms}",
    "# HELP vpn_warp_last_check_timestamp Unix time of last WARP check",
    "# TYPE vpn_warp_last_check_timestamp gauge",
    f"vpn_warp_last_check_timestamp {now}",
]
if quota_bytes >= 0:
    lines.extend([
        "# HELP vpn_warp_quota_bytes WARP premium quota bytes from Cloudflare API (-1 if unknown)",
        "# TYPE vpn_warp_quota_bytes gauge",
        f"vpn_warp_quota_bytes {quota_bytes}",
    ])
if premium_data_bytes >= 0:
    lines.extend([
        "# HELP vpn_warp_premium_data_bytes WARP premium data used bytes from Cloudflare API",
        "# TYPE vpn_warp_premium_data_bytes gauge",
        f"vpn_warp_premium_data_bytes {premium_data_bytes}",
    ])
safe_type = re.sub(r'[^a-zA-Z0-9_.-]', '_', account_type)[:64] or "unknown"
safe_license = re.sub(r'[^a-zA-Z0-9_.-]', '_', license)[:64] or "unknown"
lines.extend([
    "# HELP vpn_warp_info WARP account metadata (value always 1)",
    "# TYPE vpn_warp_info gauge",
    f'vpn_warp_info{{account_type="{safe_type}",license="{safe_license}"}} 1',
])
if cf_error:
    safe_err = re.sub(r'["\\]', "_", cf_error)[:80]
    lines.append(f'vpn_warp_last_error{{message="{safe_err}"}} 1')

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PY

mv -f "$TMP" "$OUT"
chmod 644 "$OUT" 2>/dev/null || true
EOS
  chmod 755 /usr/local/sbin/vpn-warp-check.sh

  cat > /etc/systemd/system/vpn-warp-check.service <<'UNIT'
[Unit]
Description=Collect Cloudflare WARP metrics for Prometheus
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-/etc/default/vpn-warp-check
ExecStart=/usr/local/sbin/vpn-warp-check.sh
UNIT

  cat > /etc/systemd/system/vpn-warp-check.timer <<'UNIT'
[Unit]
Description=Periodic Cloudflare WARP metrics collection

[Timer]
OnBootSec=90
OnUnitActiveSec=120
Persistent=true

[Install]
WantedBy=timers.target
UNIT

  if [[ ! -f /etc/default/vpn-warp-check ]]; then
    cat > /etc/default/vpn-warp-check <<'EOF'
# VPN_WARP_DIR=/usr/local/etc/xray/wgcf
# VPN_NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile
EOF
    chmod 644 /etc/default/vpn-warp-check
  fi

  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable vpn-warp-check.timer 2>/dev/null || true
    systemctl restart vpn-warp-check.timer 2>/dev/null || true
    systemctl start vpn-warp-check.service 2>/dev/null || true
    echo "[warp] мониторинг: timer vpn-warp-check (2 мин), метрики в $(_warp_textfile_dir)/warp.prom"
  else
    /usr/local/sbin/vpn-warp-check.sh || true
  fi
}

_warp_cleanup() {
  echo "[cleanup] warp: остановка мониторинга…"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop vpn-warp-check.timer 2>/dev/null || true
    systemctl disable vpn-warp-check.timer 2>/dev/null || true
    systemctl stop vpn-warp-check.service 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/vpn-warp-check.service
  rm -f /etc/systemd/system/vpn-warp-check.timer
  rm -f /usr/local/sbin/vpn-warp-check.sh
  rm -f /etc/default/vpn-warp-check
  rm -f "$(_warp_textfile_dir)/warp.prom"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
  fi
  echo "[cleanup] warp: удаление wgcf…"
  rm -rf "$(_warp_dir)"
  rm -f "$(_warp_wgcf_bin)"
}
