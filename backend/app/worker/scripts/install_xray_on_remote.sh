#!/usr/bin/env bash
# Удалённый хост: root. Режим: VPN_PROVISION_COMPONENT = all | xray | sync_clients | prometheus | fair_egress | cleanup
# Каскад РФ: при VPN_CASCADE_RU_DIRECT=1 — direct для private / *.ru,*.su,*.рф (punycode) / geoip:ru, остальное → egress.
# Доп. RU-сервисы вне .ru/.su:
#   1) файл VPN_CASCADE_RU_DIRECT_DOMAINS_FILE (по умолчанию рядом со скриптом: ru_direct_extra_domains.txt),
#      формат: один элемент Xray на строку (комментарии с #; без префикса => domain:<host>);
#   2) fallback: VPN_CASCADE_RU_DIRECT_EXTRA_DOMAINS (CSV/space/semicolon), если файл отсутствует/пустой.
# geosite:ru в Xray 26.2+ часто падает (code RU not found) — не используем, см. inline regexp в config.
# Gemini / мультимодальные сервисы Google: внутренний DNS (DoH) + sniffing (вкл. QUIC) + правила доменов первыми;
#   при каскаде Gemini → egress-cascade (не direct на РФ-входе). См. https://habr.com/ru/articles/992380/
# all/xray: curl/wget, python3. prometheus: curl, systemctl. cleanup: curl/wget для uninstall xray.
#
# Справедливость uplink (между TCP/UDP-потоками, не «на UUID Xray»):
#   VPN_INSTALL_FAIR_EGRESS — для all/xray: 1 (по умолчанию) ставит CAKE или fq_codel на интерфейс default route.
#   fair_egress — только перенастроить очередь (systemd vpn-egress-fairness).
# Настройки в /etc/default/vpn-egress-fairness:
#   VPN_EGRESS_IFACE — явный интерфейс (иначе авто по ip route)
#   VPN_EGRESS_BANDWIDTH — для CAKE, напр. 900mbit (≈95% от лимита VPS — уменьшает буферизацию)
# REALITY spiderX (путь к ресурсу на dest): VPN_REALITY_SPIDER_X (по умолчанию /); каскад — VPN_CASCADE_EGRESS_SPIDER_X.

set -euo pipefail

# Неинтерактивный SSH часто без TERM; XTLS install-release.sh вызывает tput → ненулевой код и обрыв при set -e.
export TERM="${TERM:-xterm-256color}"

INSTALLER_URL="${VPN_XRAY_INSTALLER_URL:-https://github.com/XTLS/Xray-install/raw/main/install-release.sh}"
COMPONENT="${VPN_PROVISION_COMPONENT:-all}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    "policy": {
        "levels": {
            "0": {
                "statsUserUplink": True,
                "statsUserDownlink": True,
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
                },
            },
        },
    ],
    "outbounds": [
        {"protocol": "freedom", "tag": "direct", "settings": {"domainStrategy": "UseIPv4"}},
    ],
}

cfg["dns"] = {
    "servers": [
        "https://1.1.1.1/dns-query",
        {
            "address": "77.88.8.8",
            "domains": [
                "geosite:ru",
                "regexp:.*\\.ru$",
                "regexp:.*\\.su$",
                "regexp:.*\\.xn--p1ai$"
            ]
        }
    ],
    "queryStrategy": "UseIPv4",
}

cascade = (os.environ.get("VPN_CASCADE_ENABLED") or "").strip() == "1"
ru_direct = cascade and (os.environ.get("VPN_CASCADE_RU_DIRECT") or "1").strip() == "1"
# routeOnly=False: подмена dest после sniff (лучше HTTP/3 и вызовы без SNI); при RU split теоретически хуже edge cases.
cfg["inbounds"][0]["sniffing"] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
    "routeOnly": False,
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
            },
        },
    }
    direct_out = {
        "protocol": "freedom",
        "tag": "direct",
        "settings": {"domainStrategy": "UseIPv4"},
    }
    cfg["outbounds"] = [vless_to_exit, direct_out]
    cfg["inbounds"][0]["tag"] = "vless-in"
    # РФ-ресурсы: прямой выход; остальное (иностранные) — через VLESS к exit
    if ru_direct:
        # Без geosite:ru: в Xray 26.2+ несовпадение кода RU/ru в geosite.dat. Замена: TLD-регэксп + geoip:ru
        # (Loyalsoldier geosite:ru тоже может не находиться). Инофисные .com и т.д. пойдут в каскад, RU-IP — через geoip:ru
        _ru_domains = [
            "geosite:private",
            *extra_ru_domains,
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
    cfg["routing"] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": [gemini_rule, gemini_google_ip_rule],
    }

path = os.environ.get("VPN_XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY
}

# Каталог для dat (кладутся install-release); split RU использует geosite:private+regexp+geoip:ru из дефолтных файлов
_xray_ensure_geo_dats() {
  if [[ "${VPN_CASCADE_RU_DIRECT:-1}" == "0" ]]; then
    echo "[xray] geo: VPN_CASCADE_RU_DIRECT=0 — dat для split RU не обязателен"
    return 0
  fi
  local dir
  dir="${VPN_XRAY_GEO_DIR:-/usr/local/share/xray}"
  mkdir -p "$dir"
  echo "[xray] geo: split RU — используются geosite.dat/geoip.dat из XTLS install (без geosite:ru, см. regexp в config)"
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
}

_ne_install() {
  if [[ "${VPN_INSTALL_NODE_EXPORTER:-1}" == "0" ]]; then
    echo "[node_exporter] отключено (VPN_INSTALL_NODE_EXPORTER=0)"
    return 0
  fi
  if [[ "${VPN_INSTALL_NODE_EXPORTER}" == "false" ]]; then
    echo "[node_exporter] отключено"
    return 0
  fi
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

_egress_fairness_install() {
  if [[ "${VPN_INSTALL_FAIR_EGRESS:-1}" == "0" || "${VPN_INSTALL_FAIR_EGRESS:-}" == "false" ]]; then
    echo "[egress_fairness] пропуск (VPN_INSTALL_FAIR_EGRESS отключён)"
    return 0
  fi
  if ! command -v tc >/dev/null 2>&1; then
    echo "[egress_fairness] нет tc (пакет iproute2) — apt-get install -y iproute2" >&2
    return 1
  fi

  install -d -m 755 /usr/local/sbin 2>/dev/null || mkdir -p /usr/local/sbin

  cat > /usr/local/sbin/vpn-egress-fairness-apply.sh <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
if [[ -f /etc/default/vpn-egress-fairness ]]; then
  set -a
  # shellcheck source=/dev/null
  source /etc/default/vpn-egress-fairness
  set +a
fi
IFACE="${VPN_EGRESS_IFACE:-}"
if [[ -z "$IFACE" ]]; then
  IFACE=$(ip -4 route show default | awk '/^default/ {print $5; exit}')
fi
if [[ -z "$IFACE" ]]; then
  echo "[vpn-egress-fairness] не найден интерфейс default route" >&2
  exit 1
fi
if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "[vpn-egress-fairness] интерфейс $IFACE не существует" >&2
  exit 1
fi
modprobe sch_cake 2>/dev/null || true
BW="${VPN_EGRESS_BANDWIDTH:-}"
cake_ok=0
if [[ -n "$BW" ]]; then
  if tc qdisc replace dev "$IFACE" root cake bandwidth "$BW" besteffort 2>/dev/null; then
    cake_ok=1
  elif tc qdisc replace dev "$IFACE" root cake bandwidth "$BW" 2>/dev/null; then
    cake_ok=1
  fi
else
  if tc qdisc replace dev "$IFACE" root cake besteffort 2>/dev/null; then
    cake_ok=1
  elif tc qdisc replace dev "$IFACE" root cake 2>/dev/null; then
    cake_ok=1
  fi
fi
if [[ "$cake_ok" -eq 1 ]]; then
  echo "[vpn-egress-fairness] CAKE на $IFACE${BW:+ bandwidth=$BW}"
  exit 0
fi
if tc qdisc replace dev "$IFACE" root fq_codel 2>/dev/null; then
  echo "[vpn-egress-fairness] fq_codel на $IFACE (модуль CAKE недоступен; на Ubuntu: linux-modules-extra-$(uname -r))"
  exit 0
fi
echo "[vpn-egress-fairness] не удалось применить qdisc" >&2
exit 1
EOS
  chmod 755 /usr/local/sbin/vpn-egress-fairness-apply.sh

  cat > /usr/local/sbin/vpn-egress-fairness-remove.sh <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
if [[ -f /etc/default/vpn-egress-fairness ]]; then
  set -a
  # shellcheck source=/dev/null
  source /etc/default/vpn-egress-fairness
  set +a
fi
IFACE="${VPN_EGRESS_IFACE:-}"
if [[ -z "$IFACE" ]]; then
  IFACE=$(ip -4 route show default | awk '/^default/ {print $5; exit}')
fi
[[ -n "$IFACE" ]] || exit 0
tc qdisc del dev "$IFACE" root 2>/dev/null || true
EOS
  chmod 755 /usr/local/sbin/vpn-egress-fairness-remove.sh

  # Держите в синхроне с app/worker/scripts/check_egress_fairness.sh
  cat > /usr/local/sbin/vpn-egress-fairness-check.sh <<'EOSCHK'
#!/usr/bin/env bash
# Проверка справедливой очереди на uplink (CAKE / fq_codel / fq) на Linux.
# Не нагрузочный тест: только конфигурация tc и (если есть) сервис vpn-egress-fairness.
#
# Запуск: /usr/local/sbin/vpn-egress-fairness-check.sh
# Сохранить снимок: ... | tee /root/egress-check-before.txt

set -uo pipefail

QUIET=0
LOG_APPEND=""
IFACE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iface)
      IFACE_OVERRIDE="${2:?}"
      shift 2
      ;;
    --log-append)
      LOG_APPEND="${2:?}"
      shift 2
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $1 (см. --help)" >&2
      exit 2
      ;;
  esac
done

_detect_iface() {
  if [[ -n "$IFACE_OVERRIDE" ]]; then
    echo "$IFACE_OVERRIDE"
    return
  fi
  if [[ -f /etc/default/vpn-egress-fairness ]]; then
    set -a
    # shellcheck source=/dev/null
    source /etc/default/vpn-egress-fairness
    set +a
  fi
  if [[ -n "${VPN_EGRESS_IFACE:-}" ]]; then
    echo "$VPN_EGRESS_IFACE"
    return
  fi
  ip -4 route show default 2>/dev/null | awk '/^default/ {print $5; exit}'
}

_classify_root() {
  local dev="$1"
  local line
  line=$(tc qdisc show dev "$dev" root 2>/dev/null | head -1 || true)
  if [[ -z "$line" ]]; then
    echo "none|"
    return
  fi
  if [[ "$line" =~ qdisc[[:space:]]+cake([[:space:]]|$) ]]; then
    echo "cake|$line"
    return
  fi
  if [[ "$line" =~ qdisc[[:space:]]+fq_codel([[:space:]]|$) ]]; then
    echo "fq_codel|$line"
    return
  fi
  if [[ "$line" =~ qdisc[[:space:]]+fq([[:space:]]|$) ]]; then
    echo "fq|$line"
    return
  fi
  echo "other|$line"
}

if ! command -v tc >/dev/null 2>&1; then
  [[ "$QUIET" -eq 1 ]] || echo "FAIL: нет tc (iproute2)" >&2
  exit 1
fi

IFACE=$(_detect_iface)
if [[ -z "$IFACE" ]]; then
  [[ "$QUIET" -eq 1 ]] || echo "FAIL: не удалось определить интерфейс (нет default route?)" >&2
  exit 1
fi

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  [[ "$QUIET" -eq 1 ]] || echo "FAIL: интерфейс $IFACE не существует" >&2
  exit 1
fi

IFS='|' read -r KIND ROOTLINE <<<"$(_classify_root "$IFACE")"

FAIR=0
case "$KIND" in
  cake|fq_codel|fq) FAIR=1 ;;
esac

if [[ "$QUIET" -ne 1 ]]; then
  echo "=== Проверка egress fairness ==="
  echo "Интерфейс (uplink): $IFACE"
  echo "Root qdisc:         $KIND"
  echo "Строка tc root:     $ROOTLINE"
  echo
  echo "--- tc qdisc (root) ---"
  tc qdisc show dev "$IFACE" root 2>/dev/null || true
  echo
  echo "--- tc -s qdisc (root, счётчики) ---"
  tc -s qdisc show dev "$IFACE" root 2>/dev/null || true
  echo
  if command -v systemctl >/dev/null 2>&1; then
    echo "--- systemd vpn-egress-fairness ---"
    systemctl status vpn-egress-fairness.service --no-pager 2>/dev/null || echo "(юнит не найден или нет прав)"
    echo
  fi
  if [[ -f /etc/default/vpn-egress-fairness ]]; then
    echo "--- /etc/default/vpn-egress-fairness (активные строки) ---"
    grep -E '^[[:space:]]*[^#]' /etc/default/vpn-egress-fairness 2>/dev/null || true
    echo
  fi
  if [[ "$FAIR" -eq 1 ]]; then
    echo "Итог: OK — на uplink стоит справедливая очередь ($KIND)."
  else
    echo "Итог: FAIL — ожидались cake / fq_codel / fq на root, сейчас: $KIND."
    echo "       До провижининга обычно видно pfifo_fast или другой «other»."
  fi
fi

if [[ -n "$LOG_APPEND" ]]; then
  ts=$(date -Iseconds 2>/dev/null || date)
  if [[ "$FAIR" -eq 1 ]]; then
    echo "$ts $IFACE $KIND OK" >>"$LOG_APPEND"
  else
    echo "$ts $IFACE $KIND FAIL" >>"$LOG_APPEND"
  fi
fi

[[ "$QUIET" -eq 1 ]] && { [[ "$FAIR" -eq 1 ]] && echo OK || echo FAIL; }

exit $((1 - FAIR))
EOSCHK
  chmod 755 /usr/local/sbin/vpn-egress-fairness-check.sh

  if [[ ! -f /etc/default/vpn-egress-fairness ]]; then
    cat > /etc/default/vpn-egress-fairness <<'EOF'
# Справедливая очередь на исходящем интерфейсе (после перезагрузки — systemd).
# Один клиент с многими параллельными загрузками всё ещё может взять больше полосы, чем клиент с одним потоком.
#
# VPN_EGRESS_IFACE=ens3
# VPN_EGRESS_BANDWIDTH=950mbit
EOF
    chmod 644 /etc/default/vpn-egress-fairness
  fi

  if command -v systemctl >/dev/null 2>&1; then
    cat > /etc/systemd/system/vpn-egress-fairness.service <<'UNIT'
[Unit]
Description=VPN egress fair queue (CAKE / fq_codel on default route iface)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/default/vpn-egress-fairness
ExecStart=/usr/local/sbin/vpn-egress-fairness-apply.sh
ExecStop=/usr/local/sbin/vpn-egress-fairness-remove.sh

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable vpn-egress-fairness.service 2>/dev/null || true
    systemctl restart vpn-egress-fairness.service || true
    echo "[egress_fairness] сервис vpn-egress-fairness, см. /etc/default/vpn-egress-fairness"
    echo "[egress_fairness] проверка: /usr/local/sbin/vpn-egress-fairness-check.sh"
  else
    echo "[egress_fairness] нет systemctl — однократный запуск apply…"
    /usr/local/sbin/vpn-egress-fairness-apply.sh || true
    echo "[egress_fairness] проверка: /usr/local/sbin/vpn-egress-fairness-check.sh"
  fi
}

_egress_fairness_purge() {
  echo "[cleanup] vpn-egress-fairness: остановка и снятие qdisc…"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop vpn-egress-fairness.service 2>/dev/null || true
    systemctl disable vpn-egress-fairness.service 2>/dev/null || true
  fi
  if [[ -x /usr/local/sbin/vpn-egress-fairness-remove.sh ]]; then
    /usr/local/sbin/vpn-egress-fairness-remove.sh 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/vpn-egress-fairness.service
  rm -f /usr/local/sbin/vpn-egress-fairness-apply.sh
  rm -f /usr/local/sbin/vpn-egress-fairness-remove.sh
  rm -f /usr/local/sbin/vpn-egress-fairness-check.sh
  rm -f /etc/default/vpn-egress-fairness
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
  fi
}

_cleanup() {
  _egress_fairness_purge
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
  sync_clients)
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
    ;;
  xray)
    _xray_install
    _egress_fairness_install
    _emit_meta
    ;;
  fair_egress)
    VPN_INSTALL_FAIR_EGRESS=1 _egress_fairness_install
    ;;
  prometheus|node_exporter)
    _ne_install
    ;;
  all|*)
    _xray_install
    _egress_fairness_install
    _ne_install
    _emit_meta
    ;;
esac

echo "[provision] завершено (${COMPONENT})."
