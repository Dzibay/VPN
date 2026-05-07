-- Базовые таблицы для пустой БД (CREATE IF NOT EXISTS).
-- Патчи для старых инстансов, ALTER и индексы — в migrate.sql.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT,
    telegram_properties JSONB,
    email TEXT,
    password_hash TEXT,
    subscription_until DATE,
    account_role TEXT NOT NULL DEFAULT 'client',
    token TEXT NOT NULL,
    vless_uuid TEXT NOT NULL,
    CONSTRAINT users_token_key UNIQUE (token),
    CONSTRAINT users_vless_uuid_key UNIQUE (vless_uuid),
    CONSTRAINT users_account_role_check CHECK (account_role IN ('client', 'manager', 'admin'))
);

CREATE TABLE IF NOT EXISTS servers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 443 CHECK (port >= 1 AND port <= 65535),
    country TEXT NOT NULL DEFAULT '',
    load_percent INTEGER NOT NULL DEFAULT 0 CHECK (load_percent >= 0 AND load_percent <= 100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    whitelist BOOLEAN NOT NULL DEFAULT FALSE,
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
    is_cascade_ru_entry BOOLEAN NOT NULL DEFAULT FALSE,
    cascade_next_server_id BIGINT REFERENCES servers (id) ON DELETE SET NULL,
    CONSTRAINT uq_servers_host_port UNIQUE (host, port),
    CONSTRAINT ck_servers_cascade_ru_and_next CHECK (
        cascade_next_server_id IS NULL OR is_cascade_ru_entry = TRUE
    ),
    -- UUID VLESS с РФ-входа на внешний exit (должен быть в inbound exit вместе с пользователями)
    cascade_egress_client_uuid TEXT,
    CONSTRAINT uq_servers_cascade_egress_uuid UNIQUE (cascade_egress_client_uuid)
);

CREATE TABLE IF NOT EXISTS user_server_traffic (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    server_id BIGINT NOT NULL REFERENCES servers (id) ON DELETE CASCADE,
    traffic_date DATE NOT NULL,
    up_bytes BIGINT NOT NULL DEFAULT 0,
    down_bytes BIGINT NOT NULL DEFAULT 0,
    raw_up BIGINT NOT NULL DEFAULT 0,
    raw_down BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, server_id, traffic_date)
);
