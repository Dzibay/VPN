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

curl -fsS "http://api:8000/api/edge/placeholder-domains" 2>/dev/null | while IFS= read -r domain; do
  domain="$(printf '%s' "$domain" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$domain" ] && continue
  cat >> "$CONFIG" <<EOF

# Заглушка проекта (brand.frontend_mode=placeholder); /api → backend для бота.
${domain} {
    encode gzip zstd

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    forward_auth http://api:8000 {
        uri /api/tls/ask?domain={host}
    }

    reverse_proxy nginx-halyal:80
}
EOF
done

exec caddy run --config "$CONFIG" --adapter caddyfile "$@"
