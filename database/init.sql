-- Клиенты VPN-сервиса (учётные записи, привязка к Telegram, подписка, токен доступа)
-- telegram_id: числовой id пользователя в Telegram (Bot API). Пусто = NULL, несколько NULL допустимо.
-- telegram_properties: JSON (ник, locale и т.д.)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT,
    telegram_properties JSONB,
    email TEXT,
    password_hash TEXT,
    subscription_until DATE,
    token TEXT NOT NULL,
    vless_uuid TEXT NOT NULL,
    CONSTRAINT users_token_key UNIQUE (token),
    CONSTRAINT users_vless_uuid_key UNIQUE (vless_uuid)
);

-- Миграция для уже существующих БД (до появления колонок в CREATE выше)
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_properties JSONB;

-- Уникальность только для непустых telegram_id (несколько NULL допустимо)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)
    WHERE telegram_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)
    WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_subscription_until ON users (subscription_until);

-- Узлы прокси (xray и т.п.): адрес для выдачи в подписке и учёта в админке
CREATE TABLE IF NOT EXISTS servers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 443 CHECK (port >= 1 AND port <= 65535),
    country TEXT NOT NULL DEFAULT '',
    load_percent INTEGER NOT NULL DEFAULT 0 CHECK (load_percent >= 0 AND load_percent <= 100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    provision_ready BOOLEAN NOT NULL DEFAULT FALSE,
    provision_status TEXT NOT NULL DEFAULT 'idle',
    provision_error TEXT,
    provision_job_id TEXT,
    vless_uuid TEXT NOT NULL,
    reality_private_key TEXT,
    reality_public_key TEXT,
    reality_short_id TEXT NOT NULL,
    reality_dest TEXT NOT NULL DEFAULT 'www.amazon.com:443',
    reality_server_names TEXT NOT NULL DEFAULT 'www.amazon.com,amazon.com',
    reality_fingerprint TEXT NOT NULL DEFAULT 'chrome',
    vless_flow TEXT NOT NULL DEFAULT 'xtls-rprx-vision',
    prometheus_instance TEXT,
    network_cap_mbps INTEGER CHECK (
        network_cap_mbps IS NULL OR (network_cap_mbps >= 1 AND network_cap_mbps <= 1000000)
    ),
    CONSTRAINT uq_servers_host_port UNIQUE (host, port)
);

CREATE INDEX IF NOT EXISTS idx_servers_is_active ON servers (is_active);

-- Накопленный трафик по паре (пользователь, узел); raw_* — последние сырые счётчики Xray
CREATE TABLE IF NOT EXISTS user_server_traffic (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    server_id BIGINT NOT NULL REFERENCES servers (id) ON DELETE CASCADE,
    up_bytes BIGINT NOT NULL DEFAULT 0,
    down_bytes BIGINT NOT NULL DEFAULT 0,
    raw_up BIGINT NOT NULL DEFAULT 0,
    raw_down BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, server_id)
);

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_server ON user_server_traffic (server_id);
