#!/bin/sh
# Caddy: ADMIN_SITE_ADDRESS из env; домены заглушек — из API + PLACEHOLDER_FRONTEND_DOMAINS.
set -eu

if ! command -v curl >/dev/null 2>&1; then
  apk add --no-cache curl >/dev/null 2>&1 || true
fi

CONFIG=/tmp/Caddyfile.runtime
cp /etc/caddy/Caddyfile "$CONFIG"

TRIES=45
while [ "$TRIES" -gt 0 ]; do
  if curl -fsS "http://api:8000/api/health" >/dev/null 2>&1; then
    break
  fi
  TRIES=$((TRIES - 1))
  sleep 2
done

PH_FILE=/tmp/placeholder.caddy
DOMAINS_FILE=/tmp/placeholder-domains.txt
: > "$DOMAINS_FILE"

TRIES=45
while [ "$TRIES" -gt 0 ]; do
  if curl -fsS "http://api:8000/api/edge/placeholder-domains" >"$DOMAINS_FILE" 2>/dev/null \
    && [ -s "$DOMAINS_FILE" ]; then
    break
  fi
  : > "$DOMAINS_FILE"
  TRIES=$((TRIES - 1))
  sleep 2
done

if [ -n "${PLACEHOLDER_FRONTEND_DOMAINS:-}" ]; then
  printf '%s\n' "$PLACEHOLDER_FRONTEND_DOMAINS" | tr ',' '\n' >>"$DOMAINS_FILE"
fi

HOSTS=""
while IFS= read -r domain; do
  domain="$(printf '%s' "$domain" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$domain" ] && continue
  case " ${HOSTS} " in
    *" ${domain} "*) ;;
    *) HOSTS="${HOSTS} ${domain}" ;;
  esac
done <"$DOMAINS_FILE"

HOSTS="$(printf '%s' "$HOSTS" | sed 's/^[[:space:]]*//')"
if [ -n "$HOSTS" ]; then
  cat >"$PH_FILE" <<EOF
    @placeholder host ${HOSTS}
    handle @placeholder {
        reverse_proxy nginx-halyal:80
    }

EOF
  echo "caddy: placeholder hosts:${HOSTS}" >&2
else
  : >"$PH_FILE"
  echo "caddy: no placeholder frontend domains (API + PLACEHOLDER_FRONTEND_DOMAINS empty)" >&2
fi

sed -e "/PLACEHOLDER_HANDLES_MARKER/r $PH_FILE" -e "/PLACEHOLDER_HANDLES_MARKER/d" "$CONFIG" > "${CONFIG}.new"
mv "${CONFIG}.new" "$CONFIG"

exec caddy run --config "$CONFIG" --adapter caddyfile "$@"
