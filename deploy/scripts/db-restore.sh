#!/usr/bin/env bash
# Восстановление PostgreSQL из gzip-дампа (pg_dump) на новом сервере.
# Запуск из каталога deploy/ после первого `docker compose up -d postgres`:
#   ./scripts/db-restore.sh ./vpn-db-20260101T120000Z.sql.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup.sql.gz>" >&2
  exit 1
fi

DUMP="$1"
if [[ ! -f "$DUMP" ]]; then
  echo "Файл не найден: $DUMP" >&2
  exit 1
fi

echo "Поднимаем postgres (если ещё не запущен)…"
docker compose up -d postgres

# shellcheck disable=SC1091
source "${ROOT}/scripts/load-postgres-env.sh"

echo "Ждём готовности postgres…"
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-vpn}" -d "${POSTGRES_DB:-vpn}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

load_postgres_env

if ! docker compose exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
  echo "Postgres не ответил за 2 минуты." >&2
  exit 1
fi

echo "Пересоздаём базу ${POSTGRES_DB} (данные init.sql будут заменены дампом)…"
docker compose exec -T postgres \
  psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS ${POSTGRES_DB} WITH (FORCE);
CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};
SQL

echo "Восстанавливаем из ${DUMP}…"
gunzip -c "${DUMP}" | docker compose exec -T postgres \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -q

echo "Готово. Поднимите весь стек:"
echo "  docker compose up -d --build"
