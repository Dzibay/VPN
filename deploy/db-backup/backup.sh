#!/usr/bin/env bash
# Ежедневный логический дамп PostgreSQL → gzip → Яндекс Диск (WebDAV).
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${YANDEX_DISK_USER:?YANDEX_DISK_USER is required}"
: "${YANDEX_DISK_PASSWORD:?YANDEX_DISK_PASSWORD is required}"

export PGPASSWORD="${POSTGRES_PASSWORD}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FOLDER="${YANDEX_DISK_FOLDER:-vpn-db-backups}"
FILENAME="vpn-db-${TIMESTAMP}.sql.gz"
TMP="$(mktemp)"

cleanup() {
  rm -f "$TMP"
}
trap cleanup EXIT

RCLONE_CONFIG="${RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"
mkdir -p "$(dirname "$RCLONE_CONFIG")"
rm -f "$RCLONE_CONFIG"
OBSCURED="$(printf '%s' "${YANDEX_DISK_PASSWORD}" | rclone obscure --stdin-no-entities -)"
rclone config create ydisk webdav url https://webdav.yandex.ru vendor other \
  user "${YANDEX_DISK_USER}" pass "${OBSCURED}"
chmod 600 "$RCLONE_CONFIG"

pg_dump -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --no-owner --no-acl | gzip -9 -c >"$TMP"

rclone mkdir "ydisk:${FOLDER}" 2>/dev/null || true
rclone copyto "$TMP" "ydisk:${FOLDER}/${FILENAME}" --retries 5 --low-level-retries 10

echo "$(date -u -Iseconds) uploaded ydisk:${FOLDER}/${FILENAME}"
