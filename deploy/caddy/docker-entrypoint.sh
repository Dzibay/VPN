#!/bin/sh
set -eu

ADDRESSES="${SITE_ADDRESS}"
if [ -n "${SITE_EXTRA_ADDRESSES:-}" ]; then
  ADDRESSES="${ADDRESSES}, ${SITE_EXTRA_ADDRESSES}"
fi
export SITE_ALL_ADDRESSES="${ADDRESSES}"

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile "$@"
