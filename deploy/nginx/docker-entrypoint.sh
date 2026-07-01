#!/bin/sh
# Генерирует server{} для доменов-заглушек (brand.frontend_mode=placeholder).
# Даже если Caddy не подставил @placeholder при старте, Host halyal-connect.ru
# не попадёт в общий SPA Подорожника.
set -eu

CONF=/etc/nginx/conf.d/placeholder-proxy.conf
DOMAINS_FILE=/tmp/placeholder-domains.txt
: > "$DOMAINS_FILE"

TRIES=45
while [ "$TRIES" -gt 0 ]; do
  if wget -qO- "http://api:8000/api/edge/placeholder-domains" >>"$DOMAINS_FILE" 2>/dev/null \
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

SERVER_NAMES=""
while IFS= read -r domain; do
  domain="$(printf '%s' "$domain" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$domain" ] && continue
  case " ${SERVER_NAMES} " in
    *" ${domain} "*) ;;
    *) SERVER_NAMES="${SERVER_NAMES} ${domain}" ;;
  esac
done <"$DOMAINS_FILE"

SERVER_NAMES="$(printf '%s' "$SERVER_NAMES" | sed 's/^[[:space:]]*//')"

if [ -n "$SERVER_NAMES" ]; then
  cat >"$CONF" <<EOF
# Домены-заглушки (не default_server — см. listen default_server в nginx.conf).
server {
    listen 80;
    server_name ${SERVER_NAMES};

    location / {
        proxy_pass http://nginx-halyal:80;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$forwarded_proto;
        proxy_set_header X-Forwarded-Host \$host;
    }
}
EOF
  echo "nginx: placeholder proxy hosts:${SERVER_NAMES}" >&2
else
  printf '# placeholder frontend domains: none\n' >"$CONF"
  echo "nginx: no placeholder frontend domains (API + PLACEHOLDER_FRONTEND_DOMAINS empty)" >&2
fi

exec nginx -g 'daemon off;'
