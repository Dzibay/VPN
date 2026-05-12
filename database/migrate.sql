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
    owner_user_id BIGINT REFERENCES users (id) ON DELETE CASCADE,
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_user_created_at
    ON user_http_request_traces (user_id, created_at DESC NULLS LAST)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_created_at
    ON user_http_request_traces (created_at DESC);

-- События на временной шкале графика статистики (staff: админ и менеджер)
CREATE TABLE IF NOT EXISTS staff_chart_events (
    id BIGSERIAL PRIMARY KEY,
    event_at TIMESTAMPTZ NOT NULL,
    title TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staff_chart_events_event_at
    ON staff_chart_events (event_at ASC);

-- Платежи пользователей (наличие строки = зафиксированный платёж)
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    months INTEGER NOT NULL CHECK (months >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_user_created_at
    ON payments (user_id, created_at DESC);

-- payments: провайдер tribute/manual, внешний id (подписка sub:… / покупка dp:…)
ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS external_id TEXT;

UPDATE payments SET provider = 'manual' WHERE provider IS NULL OR provider = '';

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_provider_check;
ALTER TABLE payments ADD CONSTRAINT payments_provider_check CHECK (
    provider IN ('manual', 'tribute')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tribute_purchase
    ON payments (provider, external_id)
    WHERE provider = 'tribute' AND external_id IS NOT NULL;

-- Очередь задач (уведомления / бонусы по рефералам и т.п.)
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    referee_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    bonus_days INTEGER CHECK (bonus_days IS NULL OR bonus_days >= 0),
    paid_months INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    done_at TIMESTAMPTZ,
    CONSTRAINT tasks_type_check CHECK (
        type IN (
            'notify_ref_reg',
            'notify_ref_pay',
            'notify_payment',
            'notify_sub_expire_3d',
            'notify_sub_expire_1d'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_created_at
    ON tasks (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_pending
    ON tasks (created_at ASC)
    WHERE done_at IS NULL;

-- Сервер помечен для белого списка (логика фильтрации в подписке — отдельно)
ALTER TABLE servers ADD COLUMN IF NOT EXISTS whitelist BOOLEAN NOT NULL DEFAULT FALSE;

-- REALITY spiderX (путь к dest для «паучка»); подписка / провижн
ALTER TABLE servers ADD COLUMN IF NOT EXISTS reality_spider_x TEXT NOT NULL DEFAULT '/';

-- tasks: явный статус обработки (pending/completed/failed)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check CHECK (
    status IN ('pending', 'completed', 'failed')
);
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks (status);

-- tasks: обновление старых типов задач на новую схему
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_type_check;
UPDATE tasks SET type = 'notify_ref_reg' WHERE type = 'notify_reg';
UPDATE tasks SET type = 'notify_ref_pay' WHERE type = 'add_bonus';
ALTER TABLE tasks ADD CONSTRAINT tasks_type_check CHECK (
    type IN (
        'notify_ref_reg',
        'notify_ref_pay',
        'notify_payment',
        'notify_sub_expire_3d',
        'notify_sub_expire_1d'
    )
);

-- Тип прокси на узле: vless (Xray REALITY) или hysteria2
ALTER TABLE servers ADD COLUMN IF NOT EXISTS proxy_kind TEXT NOT NULL DEFAULT 'vless';
UPDATE servers SET proxy_kind = 'hysteria2' WHERE proxy_kind = 'naive';
ALTER TABLE servers DROP CONSTRAINT IF EXISTS servers_proxy_kind_check;
ALTER TABLE servers ADD CONSTRAINT servers_proxy_kind_check CHECK (
    proxy_kind IN ('vless', 'hysteria2')
);

-- payments: удаление колонки status (миграция со старых схем)
DROP INDEX IF EXISTS idx_payments_status;
ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_status_check;
ALTER TABLE payments DROP COLUMN IF EXISTS status;

-- tasks: paid_months для notify_payment (число оплаченных месяцев)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS paid_months INTEGER;
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_paid_months_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_paid_months_check CHECK (
    paid_months IS NULL OR paid_months >= 1
);

-- referral_links: при удалении пользователя удалять его персональную ссылку (owner_kind=user),
-- иначе ON DELETE SET NULL даёт owner_user_id=NULL и ломает referral_links_owner_consistency
ALTER TABLE referral_links DROP CONSTRAINT IF EXISTS referral_links_owner_user_id_fkey;
ALTER TABLE referral_links ADD CONSTRAINT referral_links_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE CASCADE;

-- payments: тип сценария оплаты (ручная / Tribute подписка / Tribute разовая цифровая покупка)
ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_kind TEXT;
UPDATE payments SET payment_kind = CASE
    WHEN provider = 'manual' THEN 'manual'
    WHEN provider = 'tribute' AND external_id LIKE 'dp:%' THEN 'one_time'
    WHEN provider = 'tribute' THEN 'subscription'
    ELSE 'manual'
END
WHERE payment_kind IS NULL;
UPDATE payments SET payment_kind = 'manual' WHERE payment_kind IS NULL;
ALTER TABLE payments ALTER COLUMN payment_kind SET DEFAULT 'manual';
ALTER TABLE payments ALTER COLUMN payment_kind SET NOT NULL;
ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_payment_kind_check;
ALTER TABLE payments ADD CONSTRAINT payments_payment_kind_check CHECK (
    payment_kind IN ('manual', 'subscription', 'one_time')
);

-- tasks: тип notify_sub_expire_0d (последний календарный день подписки; раньше совпадал с notify_sub_expire_1d)
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_type_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_type_check CHECK (
    type IN (
        'notify_ref_reg',
        'notify_ref_pay',
        'notify_payment',
        'notify_sub_expire_3d',
        'notify_sub_expire_1d',
        'notify_sub_expire_0d',
        'notify_sub_expire'
    )
);
