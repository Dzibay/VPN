-- Патчи схемы для уже существующих БД и индексы (выполняется после init.sql).
-- При старте API/worker и при docker-entrypoint-initdb.d (02-migrate.sql).
--
-- Важно: если «перезаписываете» этот файл, не удаляйте старые идемпотентные патчи
-- (ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS), пока есть БД, которым они
-- ещё нужны. Иначе старые окружения перестанут догонять схему. Новые изменения —
-- добавляйте в конец; для необратимых шагов лучше нумерованные миграции (Alembic и т.п.).
--
-- DROP INDEX / смена индексов: при необходимости — IF EXISTS и затем CREATE.

-- users: колонки, появившиеся после первых версий таблицы
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_properties JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)
    WHERE telegram_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)
    WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_subscription_until ON users (subscription_until);

CREATE INDEX IF NOT EXISTS idx_servers_is_active ON servers (is_active);

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_server ON user_server_traffic (server_id);
