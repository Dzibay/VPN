#!/bin/sh
# Caddy: ADMIN_SITE_ADDRESS из env; домены заглушек — из API (projects.brand.frontend_mode).
set -eu

if ! command -v curl >/dev/null 2>&1; then
  apk add --no-cache curl >/dev/null 2>&1 || true
fi

CONFIG=/tmp/Caddyfile.runtime
cp /etc/caddy/Caddyfile "$CONFIG"

TRIES=30
while [ "$TRIES" -gt 0 ]; do
  if curl -fsS "http://api:8000/api/health" >/dev/null 2>&1; then
    break
  fi
  TRIES=$((TRIES - 1))
  sleep 2
done

PH_FILE=/tmp/placeholder.caddy
: > "$PH_FILE"
HOSTS=""
while IFS= read -r domain; do
  domain="$(printf '%s' "$domain" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$domain" ] && continue
  HOSTS="${HOSTS} ${domain}"
done <<EOF
$(curl -fsS "http://api:8000/api/edge/placeholder-domains" 2>/dev/null || true)
EOF

HOSTS="$(printf '%s' "$HOSTS" | sed 's/^[[:space:]]*//')"
if [ -n "$HOSTS" ]; then
  cat > "$PH_FILE" <<EOF
    @placeholder host${HOSTS}
    handle @placeholder {
        reverse_proxy nginx-halyal:80
    }

EOF
  echo "caddy: placeholder hosts:${HOSTS}" >&2
else
  echo "caddy: no placeholder frontend domains from API" >&2
fi

sed -e "/PLACEHOLDER_HANDLES_MARKER/r $PH_FILE" -e "/PLACEHOLDER_HANDLES_MARKER/d" "$CONFIG" > "${CONFIG}.new"
mv "${CONFIG}.new" "$CONFIG"

exec caddy run --config "$CONFIG" --adapter caddyfile "$@"
