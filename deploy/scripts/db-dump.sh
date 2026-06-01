#!/usr/bin/env bash
# Логический дамп PostgreSQL из работающего docker compose стека.
# Запуск из каталога deploy/:
#   ./scripts/db-dump.sh
#   ./scripts/db-dump.sh /tmp/vpn-db-backup.sql.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-vpn}"
POSTGRES_DB="${POSTGRES_DB:-vpn}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required (set in deploy/.env)}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-${ROOT}/vpn-db-${TIMESTAMP}.sql.gz}"

if ! docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
  echo "Postgres не запущен. Поднимите стек или только postgres:"
  echo "  docker compose up -d postgres"
  exit 1
fi

echo "Дамп ${POSTGRES_DB}@${POSTGRES_USER} → ${OUT}"

docker compose exec -T postgres env PGPASSWORD="${POSTGRES_PASSWORD}" \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  --no-owner --no-acl | gzip -9 -c >"${OUT}"

echo "Готово: ${OUT} ($(du -h "${OUT}" | cut -f1))"
