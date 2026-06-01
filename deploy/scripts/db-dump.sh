#!/usr/bin/env bash
# Логический дамп PostgreSQL из работающего docker compose стека.
# Запуск из каталога deploy/:
#   ./scripts/db-dump.sh
#   ./scripts/db-dump.sh /tmp/vpn-db-backup.sql.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "${ROOT}/scripts/load-postgres-env.sh"
load_postgres_env

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-${ROOT}/vpn-db-${TIMESTAMP}.sql.gz}"

echo "Дамп ${POSTGRES_DB}@${POSTGRES_USER} → ${OUT}"

docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  --no-owner --no-acl | gzip -9 -c >"${OUT}"

echo "Готово: ${OUT} ($(du -h "${OUT}" | cut -f1))"
