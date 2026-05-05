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

-- Реферальные токены (конверсия: клики / регистрации / оплаты); полная ссылка собирается из origin + token
-- owner_kind: произвольная метка (github, bot1, campaign, …); зарезервировано «user» — тогда нужен owner_user_id
CREATE TABLE IF NOT EXISTS referral_links (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL,
    owner_kind TEXT NOT NULL,
    owner_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    clicks_count BIGINT NOT NULL DEFAULT 0 CHECK (clicks_count >= 0),
    registrations_count BIGINT NOT NULL DEFAULT 0 CHECK (registrations_count >= 0),
    payments_count BIGINT NOT NULL DEFAULT 0 CHECK (payments_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT referral_links_token_key UNIQUE (token),
    CONSTRAINT referral_links_owner_consistency CHECK (
        (owner_kind = 'user' AND owner_user_id IS NOT NULL)
        OR (owner_kind <> 'user' AND owner_user_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_referral_links_owner_user_id ON referral_links (owner_user_id)
    WHERE owner_user_id IS NOT NULL;

-- Уже развёрнутые БД со старым CHECK(owner_kind IN ('user','campaign')): снять перечень и оставить только согласованность с user
ALTER TABLE referral_links DROP CONSTRAINT IF EXISTS referral_links_owner_kind_check;
ALTER TABLE referral_links DROP CONSTRAINT IF EXISTS referral_links_owner_consistency;
ALTER TABLE referral_links ADD CONSTRAINT referral_links_owner_consistency CHECK (
    (owner_kind = 'user' AND owner_user_id IS NOT NULL)
    OR (owner_kind <> 'user' AND owner_user_id IS NULL)
);

-- Привязка пользователя к реферальной ссылке с сайта (после регистрации по ?ref=)
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_link_id BIGINT REFERENCES referral_links (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_users_referral_link_id ON users (referral_link_id)
    WHERE referral_link_id IS NOT NULL;

-- Учётные роли: client | manager | admin (не делать промежуточный CHECK только на client/manager —
-- при уже назначенном admin повторный прогон migrate.sql падал бы на ADD CONSTRAINT).
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_role TEXT NOT NULL DEFAULT 'client';
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_role_check;
ALTER TABLE users ADD CONSTRAINT users_account_role_check CHECK (
    account_role IN ('client', 'manager', 'admin')
);

-- Дата и время регистрации (создания записи); для записей до миграции — NULL
ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users (registered_at DESC NULLS LAST);

-- Не более одной строки referral_links с owner_kind = user на каждого владельца (личные ссылки)
CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_links_one_user_owner
ON referral_links (owner_user_id)
WHERE owner_kind = 'user';

-- user_server_traffic: дневные строки (UTC), исторический ряд для графиков + актуальные суммы через последнюю дату
ALTER TABLE user_server_traffic ADD COLUMN IF NOT EXISTS traffic_date DATE;
UPDATE user_server_traffic
SET traffic_date = (CURRENT_TIMESTAMP AT TIME ZONE 'utc')::date
WHERE traffic_date IS NULL;
ALTER TABLE user_server_traffic ALTER COLUMN traffic_date SET NOT NULL;
ALTER TABLE user_server_traffic DROP CONSTRAINT IF EXISTS user_server_traffic_pkey;
ALTER TABLE user_server_traffic ADD PRIMARY KEY (user_id, server_id, traffic_date);
CREATE INDEX IF NOT EXISTS idx_user_server_traffic_user_day ON user_server_traffic (user_id, traffic_date DESC);

-- Устройства, с которых запрашивали подписку (уникальный fingerprint по hwid или заголовкам)
CREATE TABLE IF NOT EXISTS subscription_devices (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    user_agent TEXT,
    os TEXT,
    hwid_raw TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscription_devices_user_fp UNIQUE (user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_subscription_devices_user_updated_at
    ON subscription_devices (user_id, updated_at DESC);

-- Аудит HTTP: «цепочка» запросов по user_id + источник субъекта (jwt_* / subscription_token / anonymous).
CREATE TABLE IF NOT EXISTS user_http_request_traces (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    subject_source TEXT NOT NULL DEFAULT 'anonymous',
    http_method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL,
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_user_created_at
    ON user_http_request_traces (user_id, created_at DESC NULLS LAST)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_created_at
    ON user_http_request_traces (created_at DESC);
