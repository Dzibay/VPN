#!/usr/bin/env bash
# Читает POSTGRES_* из работающего контейнера (docker compose уже загрузил deploy/.env).
# Не использует `source .env` — значения с пробелами и спецсимволами не ломают скрипт.
set -euo pipefail

read_container_env() {
  local key="$1"
  docker compose exec -T postgres printenv "$key" 2>/dev/null | tr -d '\r'
}

ensure_postgres_running() {
  if ! docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
    echo "Postgres не запущен. Поднимите стек или только postgres:" >&2
    echo "  docker compose up -d postgres" >&2
    exit 1
  fi
}

load_postgres_env() {
  ensure_postgres_running
  POSTGRES_USER="$(read_container_env POSTGRES_USER || true)"
  POSTGRES_DB="$(read_container_env POSTGRES_DB || true)"
  POSTGRES_USER="${POSTGRES_USER:-vpn}"
  POSTGRES_DB="${POSTGRES_DB:-vpn}"
}
