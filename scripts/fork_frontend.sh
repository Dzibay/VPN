#!/usr/bin/env bash
# Форкает frontend/ в frontend-projects/<slug>/ для нового проекта.
#
# Usage:
#   ./scripts/fork_frontend.sh <slug> <domain>
#
# Что делает:
#   1. Копирует frontend/ (без node_modules и dist) в frontend-projects/<slug>/.
#   2. Правит package.json: name = "frontend-<slug>".
#   3. Готовит .env.build с SITE_ADDRESS/VITE_PUBLIC_SITE_URL для отдельной SPA-сборки.
#   4. Печатает следующие шаги (регистрация проекта в БД, deploy).
#
# Дальнейшие ручные шаги:
#   - Отредактировать стили/тексты в frontend-projects/<slug>/ (главная, брендинг).
#   - Добавить сервис nginx-<slug> в deploy/docker-compose.yml
#     (по образцу nginx: копирует Dockerfile, но подставляет FRONTEND_DIR=frontend-projects/<slug>).
#   - Направить DNS домена на сервер; Caddy выпустит TLS on-demand после проверки в API.
#   - Зарегистрировать проект в БД (см. README-multiproject.md).

set -eu

if [ "${1:-}" = "" ] || [ "${2:-}" = "" ]; then
  echo "Usage: $0 <slug> <primary_domain>" >&2
  exit 2
fi

SLUG="$1"
DOMAIN="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/frontend"
DEST="$ROOT/frontend-projects/$SLUG"

if [ ! -d "$SRC" ]; then
  echo "ERR: не найдена базовая папка $SRC" >&2
  exit 3
fi
if [ -e "$DEST" ]; then
  echo "ERR: $DEST уже существует (не буду перезаписывать)" >&2
  exit 4
fi

mkdir -p "$ROOT/frontend-projects"
echo "→ Копирую $SRC → $DEST"
rsync -a \
  --exclude='node_modules/' \
  --exclude='dist/' \
  --exclude='.vscode/' \
  --exclude='package-lock.json' \
  "$SRC"/ "$DEST"/

# Правим package.json: имя пакета.
if [ -f "$DEST/package.json" ]; then
  # sed без -i.bak для macOS/BSD совместимости.
  tmp="$(mktemp)"
  sed -e "s/\"name\": \"frontend\"/\"name\": \"frontend-$SLUG\"/" "$DEST/package.json" > "$tmp"
  mv "$tmp" "$DEST/package.json"
fi

# .env для сборки.
cat > "$DEST/.env.build" <<ENV
# Автосгенерировано fork_frontend.sh для проекта $SLUG.
SITE_ADDRESS=$DOMAIN
VITE_PUBLIC_SITE_URL=https://$DOMAIN
ENV

echo ""
echo "✔ Готово: $DEST"
echo ""
echo "Дальше вручную:"
echo ""
echo "  1) Обновите брендинг в БД:"
cat <<SQL

     INSERT INTO projects (slug, name, primary_domain, extra_domains, is_active,
                           telegram_bot_username, telegram_bot_api_secret,
                           tribute_api_key, yookassa_shop_id, yookassa_secret_key,
                           yookassa_return_url, support_telegram_username, support_email,
                           brand)
     VALUES ('$SLUG', '<Название>', '$DOMAIN', '{}'::text[], TRUE,
             '<botusername>', '<TELEGRAM_BOT_API_SECRET>',
             '<tribute_key_or_null>', '<yookassa_shop_or_null>', '<yookassa_secret_or_null>',
             'https://$DOMAIN/cabinet/pay/return',
             '<support_tg_or_null>', '<support_email_or_null>',
             '{"name": "<BrandName>"}'::jsonb);

SQL
echo "  2) Добавьте тарифы через админ-панель (/projects/<id>/tariffs)."
echo "  3) Направьте DNS $DOMAIN на сервер. Caddy получит TLS on-demand после проверки домена в API."
echo "  4) Для отдельной SPA-сборки добавьте docker-сервис nginx-$SLUG (см. deploy/README-multiproject.md)."
echo ""
