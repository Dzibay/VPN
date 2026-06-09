#!/bin/sh
set -eu

primary="${SITE_ADDRESS}"
primary="${primary#https://}"
primary="${primary#http://}"
primary="${primary%%/*}"

{
  if [ -n "${SITE_EXTRA_ADDRESSES:-}" ]; then
    printf '%s {\n    redir https://%s{uri} permanent\n}\n\n' \
      "${SITE_EXTRA_ADDRESSES}" "${primary}"
  fi
  cat /etc/caddy/Caddyfile
} > /tmp/Caddyfile

exec caddy run --config /tmp/Caddyfile --adapter caddyfile "$@"
