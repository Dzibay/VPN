-- Схема для новой БД (CREATE IF NOT EXISTS + индексы). Без ALTER: существующие инстансы уже догнаны вручную.
-- Multi-tenancy: таблицы projects/staff_users/project_tariffs создаются здесь;
-- добавление колонки project_id в существующие tenant-scoped таблицы, backfill и переезд UNIQUE-индексов —
-- в database/migrate.sql (идемпотентная миграция под гуардом schema_one_time_migrations).

-- =====================================================================
-- Multi-tenancy: корневая таблица проектов + отдельная таблица персонала.
-- =====================================================================

CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    primary_domain TEXT NOT NULL,
    extra_domains TEXT[] NOT NULL DEFAULT '{}'::text[],
    telegram_bot_username TEXT,
    telegram_bot_api_secret TEXT,
    support_telegram_username TEXT,
    support_email TEXT,
    tribute_api_key TEXT,
    yookassa_shop_id TEXT,
    yookassa_secret_key TEXT,
    yookassa_return_url TEXT,
    smtp_settings JSONB,
    referral_bonus_days_per_paid_month INTEGER,
    referral_fixed_first_payment_bonus_rub INTEGER,
    referral_bonus_policy TEXT,
    trial_days_after_registration INTEGER,
    trial_extra_days_referral_registration INTEGER,
    trial_traffic_limit_gib INTEGER,
    trial_traffic_limit_enabled BOOLEAN,
    happ_provider_id TEXT,
    subscription_sub_expire_banner JSONB,
    subscription_sub_info_banner JSONB,
    brand JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT projects_slug_key UNIQUE (slug),
    CONSTRAINT projects_primary_domain_key UNIQUE (primary_domain)
);

CREATE TABLE IF NOT EXISTS staff_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT staff_users_email_key UNIQUE (email),
    CONSTRAINT staff_users_role_check CHECK (role IN ('super_admin', 'admin', 'manager'))
);

CREATE TABLE IF NOT EXISTS staff_user_project_access (
    staff_user_id BIGINT NOT NULL REFERENCES staff_users (id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (staff_user_id, project_id),
    CONSTRAINT staff_user_project_access_role_check CHECK (role IN ('admin', 'manager'))
);

CREATE TABLE IF NOT EXISTS project_tariffs (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    months INTEGER NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    name TEXT,
    external_link TEXT,
    external_tg_link TEXT,
    external_product_id TEXT,
    kind TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT project_tariffs_provider_check CHECK (provider IN ('tribute', 'yookassa')),
    CONSTRAINT uq_project_tariffs_prov_months UNIQUE (project_id, provider, months)
);

CREATE INDEX IF NOT EXISTS idx_projects_active_slug ON projects (slug) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_staff_user_project_access_project ON staff_user_project_access (project_id);

-- Дефолтный проект id=1 для чистой инсталляции (существующие БД получат тот же id
-- через backfill в migrate.sql; примерные значения переопределяются в админке / SQL).
INSERT INTO projects (id, slug, name, primary_domain, extra_domains)
VALUES (
    1,
    'podorozhnik',
    'Подорожник VPN',
    'podorozhnik-connect.ru',
    '{}'::text[]
)
ON CONFLICT (id) DO NOTHING;

-- Sync sequence, чтобы SERIAL не дал id=1 при следующем INSERT.
SELECT setval(
    pg_get_serial_sequence('projects', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 0) FROM projects), 1),
    TRUE
);

-- Одноразовые миграции данных: гуард для migrate.sql и Python-миграций (см. schema.py).
CREATE TABLE IF NOT EXISTS schema_one_time_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- Основные таблицы
-- =====================================================================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL DEFAULT 1 REFERENCES projects (id) ON DELETE RESTRICT,
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
    referral_fixed_bonus_kopecks BIGINT CHECK (
        referral_fixed_bonus_kopecks IS NULL OR referral_fixed_bonus_kopecks >= 100
    ),
    balance_kopecks BIGINT NOT NULL DEFAULT 0 CHECK (balance_kopecks >= 0),
    support_seen_at TIMESTAMPTZ,
    email_verified_at TIMESTAMPTZ,
    CONSTRAINT users_token_key UNIQUE (token),
    CONSTRAINT users_vless_uuid_key UNIQUE (vless_uuid),
    CONSTRAINT users_account_role_check CHECK (account_role IN ('client', 'manager', 'admin')),
    CONSTRAINT users_referral_bonus_policy_check CHECK (
        referral_bonus_policy IN (
            'default',
            'fixed_first_payment_instant',
            'fixed_first_payment_balance'
        )
    )
);

CREATE TABLE IF NOT EXISTS servers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    host TEXT NOT NULL,
    ssh_user TEXT NOT NULL DEFAULT 'root',
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
    provision_step TEXT,
    provision_progress INTEGER NOT NULL DEFAULT 0 CHECK (provision_progress >= 0 AND provision_progress <= 100),
    provision_detail TEXT,
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
    origin_domain TEXT,
    cdn_domain TEXT,
    xhttp_path TEXT NOT NULL DEFAULT '/uploadfiles/',
    proxy_kind TEXT NOT NULL DEFAULT 'vless' CHECK (proxy_kind IN ('vless', 'vless_grpc', 'vless_ws', 'vless_xhttp', 'vless_vk_cdn_xhttp', 'hysteria2')),
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

CREATE TABLE IF NOT EXISTS referral_link_groups (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#58d68d',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT referral_link_groups_name_nonempty CHECK (char_length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS referral_links (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL,
    owner_kind TEXT NOT NULL,
    owner_user_id BIGINT REFERENCES users (id) ON DELETE CASCADE,
    group_id BIGINT REFERENCES referral_link_groups (id) ON DELETE SET NULL,
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
    bonus_amount_kopecks BIGINT CHECK (bonus_amount_kopecks IS NULL OR bonus_amount_kopecks >= 0),
    referral_bonus_applied BOOLEAN NOT NULL DEFAULT FALSE,
    early_payment_bonus_days INTEGER CHECK (early_payment_bonus_days IS NULL OR early_payment_bonus_days >= 0),
    paid_months INTEGER,
    delivery_channel TEXT NOT NULL DEFAULT 'telegram',
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
    CONSTRAINT tasks_delivery_channel_check CHECK (
        delivery_channel IN ('telegram', 'website', 'email')
    ),
    CONSTRAINT tasks_paid_months_check CHECK (paid_months IS NULL OR paid_months >= 1)
);

CREATE TABLE IF NOT EXISTS user_balance_ledger (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    amount_kopecks BIGINT NOT NULL CHECK (amount_kopecks <> 0),
    kind TEXT NOT NULL,
    referee_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    referee_payment_id BIGINT REFERENCES payments (id) ON DELETE SET NULL,
    task_id BIGINT REFERENCES tasks (id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_balance_ledger_kind_check CHECK (
        kind IN ('referral_first_payment')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_balance_ledger_referral_first_payment
    ON user_balance_ledger (user_id, referee_id)
    WHERE kind = 'referral_first_payment' AND referee_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_user_balance_ledger_user_id_created_at
    ON user_balance_ledger (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_project_telegram_id ON users (project_id, telegram_id)
    WHERE telegram_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_project_email ON users (project_id, email)
    WHERE email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_project_token ON users (project_id, token);

CREATE INDEX IF NOT EXISTS idx_users_project_id ON users (project_id);

CREATE INDEX IF NOT EXISTS idx_users_subscription_until ON users (subscription_until);

CREATE INDEX IF NOT EXISTS idx_users_referral_link_id ON users (referral_link_id)
    WHERE referral_link_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users (registered_at DESC NULLS LAST);

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

CREATE INDEX IF NOT EXISTS idx_payments_created_at
    ON payments (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_created_at_msk_date
    ON payments (((created_at AT TIME ZONE 'Europe/Moscow')::date));

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_date_user
    ON user_server_traffic (traffic_date, user_id);

CREATE INDEX IF NOT EXISTS idx_subscription_devices_user_created_at
    ON subscription_devices (user_id, created_at);

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

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    incurred_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    category_id BIGINT REFERENCES expense_categories (id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    note TEXT,
    payment_source TEXT NOT NULL DEFAULT 'company',
    paid_by_name TEXT,
    cash_account_id BIGINT,
    paid_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT expenses_payment_source_check CHECK (
        payment_source IN ('company', 'person', 'unpaid')
    )
);

CREATE TABLE IF NOT EXISTS cash_accounts (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'bank',
    currency TEXT NOT NULL DEFAULT 'RUB',
    opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
    opened_on DATE NOT NULL DEFAULT CURRENT_DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT cash_accounts_kind_check CHECK (
        kind IN ('bank', 'psp', 'cash', 'person', 'other')
    ),
    CONSTRAINT cash_accounts_opening_balance_check CHECK (opening_balance >= 0)
);

ALTER TABLE expenses
    ADD COLUMN IF NOT EXISTS payment_source TEXT NOT NULL DEFAULT 'company',
    ADD COLUMN IF NOT EXISTS paid_by_name TEXT,
    ADD COLUMN IF NOT EXISTS cash_account_id BIGINT,
    ADD COLUMN IF NOT EXISTS paid_on DATE;

ALTER TABLE expenses DROP CONSTRAINT IF EXISTS expenses_payment_source_check;

ALTER TABLE expenses ADD CONSTRAINT expenses_payment_source_check CHECK (
    payment_source IN ('company', 'person', 'unpaid')
);

ALTER TABLE expenses
    DROP CONSTRAINT IF EXISTS expenses_cash_account_fk;

ALTER TABLE expenses
    ADD CONSTRAINT expenses_cash_account_fk
    FOREIGN KEY (cash_account_id) REFERENCES cash_accounts (id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS cash_transactions (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES cash_accounts (id) ON DELETE RESTRICT,
    occurred_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount <> 0),
    kind TEXT NOT NULL DEFAULT 'adjustment',
    title TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT cash_transactions_kind_check CHECK (
        kind IN ('adjustment', 'transfer_in', 'transfer_out')
    )
);

CREATE TABLE IF NOT EXISTS payables (
    id BIGSERIAL PRIMARY KEY,
    counterparty_name TEXT NOT NULL,
    title TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    paid_amount NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    status TEXT NOT NULL DEFAULT 'open',
    source_type TEXT NOT NULL DEFAULT 'manual',
    expense_id BIGINT REFERENCES expenses (id) ON DELETE SET NULL,
    incurred_on DATE NOT NULL,
    due_on DATE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT payables_status_check CHECK (status IN ('open', 'partial', 'paid', 'cancelled')),
    CONSTRAINT payables_source_type_check CHECK (source_type IN ('manual', 'expense', 'referral', 'salary', 'other')),
    CONSTRAINT payables_paid_not_over_amount CHECK (paid_amount <= amount)
);

CREATE TABLE IF NOT EXISTS refunds (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT REFERENCES payments (id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    account_id BIGINT REFERENCES cash_accounts (id) ON DELETE SET NULL,
    refunded_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    net_amount NUMERIC(14, 2) NOT NULL CHECK (net_amount > 0),
    status TEXT NOT NULL DEFAULT 'succeeded',
    reason TEXT,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT refunds_status_check CHECK (status IN ('pending', 'succeeded', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS profit_withdrawals (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT REFERENCES cash_accounts (id) ON DELETE SET NULL,
    withdrawn_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    recipient_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'succeeded',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT profit_withdrawals_status_check CHECK (
        status IN ('planned', 'succeeded', 'cancelled')
    )
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by BIGINT REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_incurred_on ON expenses (incurred_on DESC);

CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category_id)
    WHERE category_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_expenses_payment_source ON expenses (payment_source);

CREATE INDEX IF NOT EXISTS idx_recurring_expenses_active ON recurring_expenses (active);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_accounts_one_default
    ON cash_accounts (is_default)
    WHERE is_default = TRUE;

CREATE INDEX IF NOT EXISTS idx_cash_transactions_account_day
    ON cash_transactions (account_id, occurred_on DESC);

CREATE INDEX IF NOT EXISTS idx_payables_status ON payables (status);

CREATE INDEX IF NOT EXISTS idx_refunds_refunded_on ON refunds (refunded_on DESC);

CREATE INDEX IF NOT EXISTS idx_profit_withdrawals_withdrawn_on
    ON profit_withdrawals (withdrawn_on DESC);

-- Seed «Основной счёт» только на чистой БД, когда таблица ещё не содержит записей и
-- миграция ещё не добавила NOT NULL project_id. Иначе (после migrate.sql) вставка
-- дефолтного счёта делается на project_id=1 (см. migrate.sql, там seed для базового проекта).
DO $seed_cash$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cash_accounts) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cash_accounts' AND column_name = 'project_id'
    ) THEN
        INSERT INTO cash_accounts (name, kind, currency, opening_balance, opened_on, active, is_default)
        VALUES ('Расчетный счет', 'bank', 'RUB', 0, CURRENT_DATE, TRUE, TRUE);
    END IF;
END
$seed_cash$;


-- Сиды категорий по умолчанию (идемпотентно).
-- Seed категорий расходов и налога по умолчанию. Оборачиваем в DO $seed$, чтобы
-- на уже мигрированной БД (project_id колонка есть, is_default может измениться)
-- не пытаться вставлять NULL project_id: миграция создаёт свои seeds для project_id=1.
DO $seed_finance$
DECLARE
    _has_project_id boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'expense_categories' AND column_name = 'project_id'
    ) INTO _has_project_id;
    IF NOT _has_project_id THEN
        INSERT INTO expense_categories (slug, title, color, sort_order)
        VALUES
            ('servers', 'Серверы и хостинг', '#38bdf8', 10),
            ('marketing', 'Маркетинг и реклама', '#f59e0b', 20),
            ('salary', 'Зарплаты и подрядчики', '#a78bfa', 30),
            ('software', 'ПО и сервисы', '#34d399', 40),
            ('support', 'Поддержка', '#f472b6', 50),
            ('other', 'Прочее', '#94a3b8', 60)
        ON CONFLICT (slug) DO NOTHING;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'app_settings' AND column_name = 'project_id'
    ) INTO _has_project_id;
    IF NOT _has_project_id THEN
        INSERT INTO app_settings (key, value)
        VALUES (
            'finance',
            '{"tax_mode": "npd", "tax_rate": 0.04, "tax_base": "gross", "currency": "RUB"}'::jsonb
        )
        ON CONFLICT (key) DO NOTHING;
    END IF;
END
$seed_finance$;

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

-- Seed SEO-страниц только до миграции v1 (иначе project_id NOT NULL).
DO $seed_seo$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'seo_pages' AND column_name = 'project_id'
    ) THEN
        INSERT INTO seo_pages (path, title, sort_order)
        VALUES
            ('/', 'Главная', 1),
            ('/vpn-dlya-youtube', 'VPN для YouTube', 10),
            ('/vpn-dlya-youtube/android', 'VPN для YouTube на Android', 11),
            ('/vpn-dlya-youtube/pc', 'VPN для YouTube на ПК', 12),
            ('/vpn-dlya-gemini', 'VPN для Gemini', 20),
            ('/vpn-dlya-telegram', 'VPN для Telegram', 30),
            ('/vpn-dlya-iphone', 'VPN для iPhone', 40),
            ('/vpn-dlya-android', 'VPN для Android', 41)
        ON CONFLICT (path) DO NOTHING;
    END IF;
END
$seed_seo$;
