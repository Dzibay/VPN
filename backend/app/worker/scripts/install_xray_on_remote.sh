#!/usr/bin/env bash
# Удалённый entrypoint. Режим: VPN_PROVISION_COMPONENT = all | xray | sync_clients | prometheus | fair_egress | cleanup | naive
#
# Функции компонентов подставляются воркером в SSH payload перед этим dispatcher:
#   provision_common.sh
#   provision_vless.sh
#   provision_naive.sh

set -euo pipefail

COMPONENT="${VPN_PROVISION_COMPONENT:-all}"

echo "[provision] component=${COMPONENT} host=$(hostname) id=${VPN_SERVER_ID:-?}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[provision] нужен root" >&2
  exit 1
fi

case "$COMPONENT" in
  cleanup)
    _cleanup_common
    _xray_cleanup
    _naive_cleanup
    echo "[cleanup] готово."
    ;;
  sync_clients)
    _xray_sync_clients
    ;;
  xray|vless)
    _xray_install
    _egress_fairness_install
    _emit_xray_meta
    ;;
  naive)
    _naive_install
    _egress_fairness_install
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
    _emit_xray_meta
    ;;
esac

echo "[provision] завершено (${COMPONENT})."
