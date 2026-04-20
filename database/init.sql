-- Клиенты VPN-сервиса (учётные записи, привязка к Telegram, подписка, токен доступа)
-- telegram_id: логин или произвольная строка. Пусто в БД = NULL, таких записей может быть несколько.
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT,
    subscription_until DATE,
    token TEXT NOT NULL,
    vless_uuid TEXT NOT NULL,
    CONSTRAINT users_token_key UNIQUE (token),
    CONSTRAINT users_vless_uuid_key UNIQUE (vless_uuid)
);

-- Уникальность только для непустых telegram_id (несколько NULL допустимо)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)
    WHERE telegram_id IS NOT NULL;

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
