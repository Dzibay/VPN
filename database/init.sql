-- Схема для новой БД (CREATE IF NOT EXISTS + индексы). Без ALTER: существующие инстансы уже догнаны вручную.

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
    registered_at TIMESTAMPTZ,
    traffic_limit_bytes BIGINT CHECK (traffic_limit_bytes IS NULL OR traffic_limit_bytes >= 0),
    -- Цикл с referral_links.owner_user_id: без REFERENCES, целостность на уровне приложения
    referral_link_id BIGINT,
    referral_bonus_policy TEXT NOT NULL DEFAULT 'default',
    support_seen_at TIMESTAMPTZ,
    email_verified_at TIMESTAMPTZ,
    CONSTRAINT users_token_key UNIQUE (token),
    CONSTRAINT users_vless_uuid_key UNIQUE (vless_uuid),
    CONSTRAINT users_account_role_check CHECK (account_role IN ('client', 'manager', 'admin')),
    CONSTRAINT users_referral_bonus_policy_check CHECK (
        referral_bonus_policy IN ('default', 'fixed_first_payment_instant')
    )
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
    include_in_auto BOOLEAN NOT NULL DEFAULT TRUE,
    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
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
    reality_spider_x TEXT NOT NULL DEFAULT '/',
    vless_flow TEXT NOT NULL DEFAULT 'xtls-rprx-vision',
    prometheus_instance TEXT,
    network_cap_mbps INTEGER CHECK (
        network_cap_mbps IS NULL OR (network_cap_mbps >= 1 AND network_cap_mbps <= 1000000)
    ),
    is_cascade_ru_entry BOOLEAN NOT NULL DEFAULT FALSE,
    cascade_next_server_id BIGINT REFERENCES servers (id) ON DELETE SET NULL,
    cascade_egress_client_uuid TEXT,
    google_routing_mode TEXT NOT NULL DEFAULT 'exit' CHECK (google_routing_mode IN ('exit', 'entry')),
    grpc_service_name TEXT NOT NULL DEFAULT 'grpc',
    tls_sni TEXT,
    ws_path TEXT NOT NULL DEFAULT '/vless',
    proxy_kind TEXT NOT NULL DEFAULT 'vless' CHECK (proxy_kind IN ('vless', 'vless_grpc', 'vless_ws', 'hysteria2')),
    CONSTRAINT uq_servers_host_port UNIQUE (host, port),
    CONSTRAINT ck_servers_cascade_ru_and_next CHECK (
        cascade_next_server_id IS NULL OR is_cascade_ru_entry = TRUE
    )
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

CREATE TABLE IF NOT EXISTS blocked_ips (
    id BIGSERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT blocked_ips_ip_key UNIQUE (ip)
);

CREATE TABLE IF NOT EXISTS user_http_request_traces (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    subject_source TEXT NOT NULL DEFAULT 'anonymous',
    http_method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL,
    client_ip TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staff_chart_events (
    id BIGSERIAL PRIMARY KEY,
    event_at TIMESTAMPTZ NOT NULL,
    title TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS support_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    author_kind TEXT NOT NULL,
    body TEXT NOT NULL,
    staff_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT support_messages_author_kind_check CHECK (
        author_kind IN ('user', 'staff')
    ),
    CONSTRAINT support_messages_body_nonempty_check CHECK (
        char_length(trim(body)) > 0
    )
);

CREATE INDEX IF NOT EXISTS ix_support_messages_user_id_created_at
    ON support_messages (user_id, created_at ASC);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users (id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    net_amount NUMERIC(14, 2) NOT NULL CHECK (net_amount >= 0),
    months INTEGER NOT NULL CHECK (months >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_webhook JSONB,
    payment_kind TEXT NOT NULL DEFAULT 'subscription',
    CONSTRAINT payments_provider_check CHECK (provider IN ('manual', 'tribute', 'yookassa')),
    CONSTRAINT payments_payment_kind_check CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    referee_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    bonus_days INTEGER CHECK (bonus_days IS NULL OR bonus_days >= 0),
    referral_bonus_applied BOOLEAN NOT NULL DEFAULT FALSE,
    early_payment_bonus_days INTEGER CHECK (early_payment_bonus_days IS NULL OR early_payment_bonus_days >= 0),
    paid_months INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    done_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    CONSTRAINT tasks_type_check CHECK (
        type IN (
            'notify_ref_reg',
            'notify_ref_pay',
            'notify_payment',
            'notify_sub_expire_3d',
            'notify_sub_expire_1d',
            'notify_sub_expire_0d',
            'notify_sub_expire',
            'notify_sub_expired_7d',
            'notify_reg_1h_has_traffic',
            'notify_reg_1h_no_traffic',
            'notify_traffic_low',
            'notify_traffic_over'
        )
    ),
    CONSTRAINT tasks_status_check CHECK (status IN ('pending', 'completed', 'failed')),
    CONSTRAINT tasks_paid_months_check CHECK (paid_months IS NULL OR paid_months >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)
    WHERE telegram_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)
    WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_subscription_until ON users (subscription_until);

CREATE INDEX IF NOT EXISTS idx_users_referral_link_id ON users (referral_link_id)
    WHERE referral_link_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users (registered_at DESC NULLS LAST);

-- Служебный узел id=0: накопление трафика с удалённых серверов (не в подписке, скрыт в админке).
-- INSERT INTO servers (
--     id,
--     name,
--     host,
--     port,
--     country,
--     load_percent,
--     is_active,
--     whitelist,
--     include_in_auto,
--     is_hidden,
--     provision_ready,
--     provision_status,
--     proxy_kind,
--     vless_uuid,
--     reality_short_id,
--     reality_dest,
--     reality_server_names,
--     reality_fingerprint,
--     reality_spider_x,
--     vless_flow,
--     is_cascade_ru_entry
-- )
-- SELECT
--     0,
--     'Архив (удалённые узлы)',
--     '__traffic_archive__',
--     1,
--     '',
--     0,
--     FALSE,
--     FALSE,
--     FALSE,
--     TRUE,
--     FALSE,
--     'idle',
--     'vless',
--     '00000000-0000-0000-0000-000000000001',
--     '00000000',
--     'www.amazon.com:443',
--     'www.amazon.com,amazon.com',
--     'chrome',
--     '/',
--     'xtls-rprx-vision',
--     FALSE
-- WHERE NOT EXISTS (SELECT 1 FROM servers WHERE id = 0);

-- SELECT setval(
--     pg_get_serial_sequence('servers', 'id'),
--     (SELECT COALESCE(MAX(id), 0) FROM servers WHERE id > 0),
--     TRUE
-- );

CREATE INDEX IF NOT EXISTS idx_servers_is_active ON servers (is_active);

CREATE INDEX IF NOT EXISTS idx_servers_cascade_next ON servers (cascade_next_server_id)
    WHERE cascade_next_server_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_servers_cascade_egress_uuid
    ON servers (cascade_egress_client_uuid)
    WHERE cascade_egress_client_uuid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_server ON user_server_traffic (server_id);

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_user_day ON user_server_traffic (user_id, traffic_date DESC);

CREATE INDEX IF NOT EXISTS idx_referral_links_owner_user_id ON referral_links (owner_user_id)
    WHERE owner_user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_links_one_user_owner
    ON referral_links (owner_user_id)
    WHERE owner_kind = 'user';

CREATE INDEX IF NOT EXISTS idx_subscription_devices_user_updated_at
    ON subscription_devices (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_user_created_at
    ON user_http_request_traces (user_id, created_at DESC NULLS LAST)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_http_request_traces_created_at
    ON user_http_request_traces (created_at);

CREATE INDEX IF NOT EXISTS idx_staff_chart_events_event_at
    ON staff_chart_events (event_at ASC);

CREATE INDEX IF NOT EXISTS idx_payments_user_created_at
    ON payments (user_id, created_at DESC);

-- uq_payments_yookassa_object_id — в migrate.sql (после tribute_webhook → provider_webhook).

CREATE INDEX IF NOT EXISTS idx_tasks_user_created_at
    ON tasks (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_pending
    ON tasks (created_at ASC)
    WHERE done_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks (status);

-- =====================================================================
-- Бухгалтерия (P&L): расходы, повторяющиеся шаблоны, категории, настройки.
-- =====================================================================

-- Категории расходов (для графиков и группировки P&L).
CREATE TABLE IF NOT EXISTS expense_categories (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#94a3b8',
    sort_order INTEGER NOT NULL DEFAULT 0,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_expense_categories_slug UNIQUE (slug)
);

-- Повторяющиеся (ежемесячные) расходы — шаблоны. В сводку разворачиваются виртуально
-- по месяцам диапазона (см. rpc_finance_accounting_summary), отдельные строки не материализуются.
CREATE TABLE IF NOT EXISTS recurring_expenses (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    category_id BIGINT REFERENCES expense_categories (id) ON DELETE SET NULL,
    note TEXT,
    day_of_month SMALLINT NOT NULL DEFAULT 1 CHECK (day_of_month BETWEEN 1 AND 28),
    start_month DATE NOT NULL,
    end_month DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT ck_recurring_expenses_month_range CHECK (
        end_month IS NULL OR end_month >= start_month
    )
);

-- Разовые расходы.
CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    incurred_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    category_id BIGINT REFERENCES expense_categories (id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL
);

-- Универсальные staff-редактируемые настройки (ключ → JSONB). Строка 'finance' — налог и валюта.
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by BIGINT REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_incurred_on ON expenses (incurred_on DESC);

CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category_id)
    WHERE category_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_recurring_expenses_active ON recurring_expenses (active);

-- Сиды категорий по умолчанию (идемпотентно).
INSERT INTO expense_categories (slug, title, color, sort_order)
VALUES
    ('servers', 'Серверы и хостинг', '#38bdf8', 10),
    ('marketing', 'Маркетинг и реклама', '#f59e0b', 20),
    ('salary', 'Зарплаты и подрядчики', '#a78bfa', 30),
    ('software', 'ПО и сервисы', '#34d399', 40),
    ('support', 'Поддержка', '#f472b6', 50),
    ('other', 'Прочее', '#94a3b8', 60)
ON CONFLICT (slug) DO NOTHING;

-- Налог по умолчанию: НПД 4% с валовой выручки (можно изменить в админке).
INSERT INTO app_settings (key, value)
VALUES (
    'finance',
    '{"tax_mode": "npd", "tax_rate": 0.04, "tax_base": "gross", "currency": "RUB"}'::jsonb
)
ON CONFLICT (key) DO NOTHING;

-- SEO-страницы: учёт переходов (views_count) для админки.
CREATE TABLE IF NOT EXISTS seo_pages (
    id BIGSERIAL PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    views_count BIGINT NOT NULL DEFAULT 0 CHECK (views_count >= 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT seo_pages_path_key UNIQUE (path)
);

INSERT INTO seo_pages (path, title, sort_order)
VALUES
    ('/', 'Главная', 1),
    ('/vpn-dlya-youtube', 'VPN для YouTube', 10),
    ('/vpn-dlya-youtube/android', 'VPN для YouTube на Android', 11),
    ('/vpn-dlya-youtube/pc', 'VPN для YouTube на ПК', 12)
ON CONFLICT (path) DO NOTHING;
