-- UUID клиента VLESS на пользователя (подписка подставляет его в ссылки; узлы — список в inbound).
-- Выполните на существующей БД после обновления кода (PostgreSQL 13+).

ALTER TABLE users ADD COLUMN IF NOT EXISTS vless_uuid TEXT;

UPDATE users
SET vless_uuid = gen_random_uuid()::text
WHERE vless_uuid IS NULL OR btrim(vless_uuid) = '';

ALTER TABLE users ALTER COLUMN vless_uuid SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_vless_uuid ON users (vless_uuid);
