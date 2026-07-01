#!/bin/sh
# Admin-domain aware entrypoint.
#
# Env:
#   ADMIN_SITE_ADDRESS           — домен админ-панели (например admin.example.com);
#                                   reverse_proxy на nginx-admin:80.
# Проектные домены не перечисляются в env: Caddy выпускает TLS on-demand,
# а backend разрешает только домены активных projects через /api/tls/ask.
set -eu

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile "$@"
