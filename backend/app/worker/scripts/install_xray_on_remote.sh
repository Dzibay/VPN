#!/usr/bin/env bash
# Удалённый entrypoint. Режим: VPN_PROVISION_COMPONENT = all | xray | sync_clients | prometheus | fair_egress | cleanup | hysteria2
#
# Функции компонентов подставляются воркером в SSH payload перед этим dispatcher:
#   provision_common.sh
#   provision_vless.sh
#   provision_vless_grpc.sh
#   provision_vless_ws.sh
#   provision_vless_xhttp.sh
#   provision_vless_vk_cdn_xhttp.sh
#   provision_warp.sh
#   provision_cascade.sh
#   provision_hysteria2.sh

set -euo pipefail

COMPONENT="${VPN_PROVISION_COMPONENT:-all}"
PROXY_KIND="${VPN_PROXY_KIND:-vless}"

echo "[provision] component=${COMPONENT} proxy=${PROXY_KIND} host=$(hostname) id=${VPN_SERVER_ID:-?} bundle=warp-monitor-v1"

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
    if [[ "$PROXY_KIND" == "vless_grpc" ]]; then
      _vless_grpc_sync_clients
    elif [[ "$PROXY_KIND" == "vless_ws" ]]; then
      _vless_ws_sync_clients
    elif [[ "$PROXY_KIND" == "vless_xhttp" ]]; then
      _vless_xhttp_sync_clients
    elif [[ "$PROXY_KIND" == "vless_vk_cdn_xhttp" ]]; then
      _vless_vkcdn_xhttp_sync_clients
    else
      _xray_sync_clients
    fi
    ;;
  xray|vless)
    if [[ "$PROXY_KIND" == "vless_grpc" ]]; then
      _vless_grpc_install
    elif [[ "$PROXY_KIND" == "vless_ws" ]]; then
      _vless_ws_install
    elif [[ "$PROXY_KIND" == "vless_xhttp" ]]; then
      _vless_xhttp_install
    elif [[ "$PROXY_KIND" == "vless_vk_cdn_xhttp" ]]; then
      _vless_vkcdn_xhttp_install
    else
      _xray_install
      _emit_xray_meta
    fi
    _egress_fairness_install
    ;;
  hysteria2)
    _hysteria2_install
    _egress_fairness_install
    ;;
  fair_egress)
    VPN_INSTALL_FAIR_EGRESS=1 _egress_fairness_install
    ;;
  warp_monitor)
    _warp_ensure_if_youtube_entry || true
    _warp_install_monitor || true
    ;;
  prometheus|node_exporter)
    _ne_install
    ;;
  all|*)
    if [[ "$PROXY_KIND" == "hysteria2" ]]; then
      _hysteria2_install
    elif [[ "$PROXY_KIND" == "vless_grpc" ]]; then
      _vless_grpc_install
    elif [[ "$PROXY_KIND" == "vless_ws" ]]; then
      _vless_ws_install
    elif [[ "$PROXY_KIND" == "vless_xhttp" ]]; then
      _vless_xhttp_install
    elif [[ "$PROXY_KIND" == "vless_vk_cdn_xhttp" ]]; then
      _vless_vkcdn_xhttp_install
    else
      _xray_install
      _emit_xray_meta
    fi
    _egress_fairness_install
    _ne_install
    ;;
esac

# YouTube entry: WARP credentials уже в _write_xray_config; здесь только мониторинг (без повторного register).
case "$COMPONENT" in
  all|xray|vless|sync_clients)
    _mode_lc=$(echo "${VPN_GOOGLE_ROUTING_MODE:-exit}" | tr '[:upper:]' '[:lower:]')
    if [[ "$_mode_lc" == "entry" ]]; then
      _warp_install_monitor || true
    fi
    ;;
esac

echo "[provision] завершено (${COMPONENT})."
