#!/usr/bin/env bash
# Общие функции удалённого провижининга: preflight, node_exporter, sysctl/fair egress и общий cleanup.

set -euo pipefail

# Неинтерактивный SSH часто без TERM; сторонние install-скрипты вызывают tput.
export TERM="${TERM:-xterm-256color}"

INSTALLER_URL="${VPN_XRAY_INSTALLER_URL:-https://github.com/XTLS/Xray-install/raw/main/install-release.sh}"
# При запуске через stdin (ssh bash -s) BASH_SOURCE[0] может быть пустым — set -u даёт «unbound variable».
_self="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$_self")" && pwd)"

# unzip/curl до install-release.sh: скрипт XTLS ставит пакеты через apt без update и с выводом в /dev/null.
_provision_preflight_packages() {
  echo "[preflight] зависимости для xray (unzip, curl, ca-certificates)…"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    set +e
    apt-get update -y 2>&1 | tail -30
    local upd_rc=$?
    apt-get install -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
      --no-install-recommends unzip curl ca-certificates ncurses-bin 2>&1 | tail -40
    local inst_rc=$?
    set -e
    if [[ "$upd_rc" -ne 0 ]]; then
      echo "[preflight] предупреждение: apt-get update код $upd_rc (зеркала/DNS?)" >&2
    fi
    if [[ "$inst_rc" -ne 0 ]]; then
      echo "[preflight] предупреждение: apt-get install код $inst_rc — при сбое xray попробуем прямую загрузку с GitHub" >&2
    fi
  elif command -v dnf >/dev/null 2>&1; then
    set +e
    dnf -y install unzip curl ca-certificates ncurses 2>&1 | tail -40
    set -e
  elif command -v yum >/dev/null 2>&1; then
    set +e
    yum -y install unzip curl ca-certificates ncurses 2>&1 | tail -40
    set -e
  elif command -v zypper >/dev/null 2>&1; then
    set +e
    zypper install -y --no-recommends unzip curl ca-certificates ncurses-utils 2>&1 | tail -40
    set -e
  else
    echo "[preflight] неизвестный менеджер пакетов — только проверка unzip/curl" >&2
  fi
  if command -v unzip >/dev/null 2>&1; then
    echo "[preflight] unzip: $(command -v unzip)"
  else
    echo "[preflight] unzip не установлен — распаковка релиза через python3 (если понадобится fallback)" >&2
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "[preflight] curl не найден — нужен для install-release и fallback" >&2
  fi
}

fetch_installer() {
  if command -v curl >/dev/null 2>&1; then
    # install-release.sh внутри снова тянет релизы с GitHub — при блокировке см. сообщение в _xray_install.
    curl -fsSL --connect-timeout 30 --max-time 300 \
      --retry 3 --retry-delay 8 --retry-all-errors \
      "$INSTALLER_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- --timeout=30 --tries=3 "$INSTALLER_URL"
  else
    echo "[provision] нужен curl или wget" >&2
    exit 1
  fi
}

# Лимиты ядра под нагрузку прокси + CAKE: ephemeral-порты, очереди accept, TFO.
_vps_net_sysctl_install() {
  if [[ "${VPN_INSTALL_NET_SYSCTL:-1}" == "0" || "${VPN_INSTALL_NET_SYSCTL:-}" == "false" ]]; then
    echo "[net_sysctl] пропуск (VPN_INSTALL_NET_SYSCTL отключён)"
    return 0
  fi
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[net_sysctl] не Linux — пропуск"
    return 0
  fi
  install -d /etc/sysctl.d 2>/dev/null || mkdir -p /etc/sysctl.d
  cat > /etc/sysctl.d/99-vpn-vps-optimize.conf <<'SYSCTL_EOF'
# VPN / proxy: снижает риск исчерпания ephemeral-портов и отвалов сокетов под нагрузкой.
# Применяется при провижининге протокола / fair_egress / all (sysctl --system).
net.ipv4.ip_local_port_range = 10000 65000
net.ipv4.tcp_tw_reuse = 1
net.core.somaxconn = 4096
net.core.netdev_max_backlog = 10000
net.ipv4.tcp_fastopen = 3
SYSCTL_EOF
  chmod 644 /etc/sysctl.d/99-vpn-vps-optimize.conf
  if command -v sysctl >/dev/null 2>&1; then
    sysctl --system >/dev/null 2>&1 || sysctl -p /etc/sysctl.d/99-vpn-vps-optimize.conf 2>/dev/null || true
  fi
  echo "[net_sysctl] записан /etc/sysctl.d/99-vpn-vps-optimize.conf (sysctl применён при возможности)"
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
  _vps_net_sysctl_install || true
  if ! command -v tc >/dev/null 2>&1; then
    echo "[egress_fairness] нет tc (пакет iproute2) — пробуем apt-get install -y iproute2" >&2
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      set +e
      apt-get install -y --no-install-recommends iproute2 2>&1 | tail -20
      set -e
    fi
    if ! command -v tc >/dev/null 2>&1; then
      echo "[egress_fairness] tc недоступен после установки iproute2" >&2
      return 1
    fi
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
  echo "[cleanup] sysctl 99-vpn-vps-optimize…"
  rm -f /etc/sysctl.d/99-vpn-vps-optimize.conf
  if command -v sysctl >/dev/null 2>&1; then
    sysctl --system >/dev/null 2>&1 || true
  fi
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

_cleanup_common() {
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
}
