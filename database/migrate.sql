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

-- Каскад: вход (РФ) → внешний exit; внешний — без собственного cascade_next
ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_cascade_ru_entry BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS cascade_next_server_id BIGINT REFERENCES servers (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_servers_cascade_next ON servers (cascade_next_server_id)
    WHERE cascade_next_server_id IS NOT NULL;

-- Инвариант: ссылка на внешний только у входа в каскаде
ALTER TABLE servers DROP CONSTRAINT IF EXISTS ck_servers_cascade_ru_and_next;
ALTER TABLE servers ADD CONSTRAINT ck_servers_cascade_ru_and_next CHECK (
    cascade_next_server_id IS NULL OR is_cascade_ru_entry = TRUE
);

-- UUID клиента: РФ-вход → VLESS+REALITY на внешний exit
ALTER TABLE servers ADD COLUMN IF NOT EXISTS cascade_egress_client_uuid TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_servers_cascade_egress_uuid
    ON servers (cascade_egress_client_uuid)
    WHERE cascade_egress_client_uuid IS NOT NULL;
