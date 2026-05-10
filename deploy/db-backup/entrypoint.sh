#!/usr/bin/env sh
# Без нужных переменных не запускаем cron — чтобы не засорять лог и не палить задачу впустую.
set -eu

MISSING=""
for var in POSTGRES_PASSWORD YANDEX_DISK_USER YANDEX_DISK_PASSWORD; do
  eval "v=\${$var:-}"
  if [ -z "$v" ]; then
    MISSING="${MISSING}${var} "
  fi
done

if [ -n "${MISSING}" ]; then
  echo "db-backup: недоступны переменные:${MISSING}— задайте их в deploy/.env и пересоздайте контейнер." >&2
  exec tail -f /dev/null
fi

exec crond -f -l 8
