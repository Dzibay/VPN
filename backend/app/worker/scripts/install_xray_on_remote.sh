#!/usr/bin/env bash
# Удалённый entrypoint. Режим: VPN_PROVISION_COMPONENT = all | xray | sync_clients | prometheus | fair_egress | cleanup | hysteria2
#
# Функции компонентов подставляются воркером в SSH payload перед этим dispatcher:
#   provision_common.sh
#   provision_vless.sh
#   provision_hysteria2.sh

set -euo pipefail

COMPONENT="${VPN_PROVISION_COMPONENT:-all}"
PROXY_KIND="${VPN_PROXY_KIND:-vless}"

echo "[provision] component=${COMPONENT} proxy=${PROXY_KIND} host=$(hostname) id=${VPN_SERVER_ID:-?}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[provision] нужен root" >&2
  exit 1
fi

case "$COMPONENT" in
  cleanup)
    _cleanup_common
    _xray_cleanup
    _hysteria2_cleanup
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
  hysteria2)
    _hysteria2_install
    _egress_fairness_install
    ;;
  fair_egress)
    VPN_INSTALL_FAIR_EGRESS=1 _egress_fairness_install
    ;;
  prometheus|node_exporter)
    _ne_install
    ;;
  all|*)
    if [[ "$PROXY_KIND" == "hysteria2" ]]; then
      _hysteria2_install
    else
      _xray_install
      _emit_xray_meta
    fi
    _egress_fairness_install
    _ne_install
    ;;
esac

echo "[provision] завершено (${COMPONENT})."
