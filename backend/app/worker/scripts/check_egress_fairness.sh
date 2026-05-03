#!/usr/bin/env bash
# Проверка справедливой очереди на uplink (CAKE / fq_codel / fq) на Linux.
# Не нагрузочный тест: только конфигурация tc и (если есть) сервис vpn-egress-fairness.
#
# После провижининга тот же скрипт на сервере:
#   /usr/local/sbin/vpn-egress-fairness-check.sh
#
# Запуск на сервере (root не обязателен для чтения tc; для systemctl — обычно да):
#   bash check_egress_fairness.sh
# С ноутбука по SSH (файл должен быть с переводами строк LF, иначе bash на Linux выдаст $'\r'):
#   Get-Content -Raw .\check_egress_fairness.sh | ssh root@HOST bash -s
#
# Сохранить снимок для сравнения глазами:
#   bash check_egress_fairness.sh | tee egress-check-before.txt
#   # после провижининга / fair_egress
#   bash check_egress_fairness.sh | tee egress-check-after.txt
#
# Опции:
#   --iface IFACE     явный интерфейс (иначе /etc/default/vpn-egress-fairness, иначе default route)
#   --log-append F    добавить строку (date -Iseconds) iface kind OK|FAIL в файл
#   --quiet           только код выхода и одна строка OK/FAIL

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
      sed -n '2,32p' "$0"
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
    echo "--- /etc/default/vpn-egress-fairness (без секретов) ---"
    grep -E '^[[:space:]]*[^#]' /etc/default/vpn-egress-fairness 2>/dev/null || true
    echo
  fi
  if [[ "$FAIR" -eq 1 ]]; then
    echo "Итог: OK — на uplink стоит справедливая очередь ($KIND)."
  else
    echo "Итог: FAIL — ожидались cake / fq_codel / fq на root, сейчас: $KIND."
    echo "       До провижининга обычно видно pfifo_fast или другой «other»."
    echo "       После: POST .../provision/fair-egress или полный provision (all/xray)."
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
