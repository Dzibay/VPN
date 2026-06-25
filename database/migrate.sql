-- Миграция для существующих инстансов.

ALTER TABLE servers
    ADD COLUMN IF NOT EXISTS ssh_user TEXT NOT NULL DEFAULT 'root';

-- Миграция для существующих инстансов: баланс и политика fixed_first_payment_balance.

-- ALTER TABLE users
--     ADD COLUMN IF NOT EXISTS referral_fixed_bonus_kopecks BIGINT CHECK (
--         referral_fixed_bonus_kopecks IS NULL OR referral_fixed_bonus_kopecks >= 100
--     );

-- ALTER TABLE users
--     ADD COLUMN IF NOT EXISTS balance_kopecks BIGINT NOT NULL DEFAULT 0 CHECK (balance_kopecks >= 0);

-- ALTER TABLE users DROP CONSTRAINT IF EXISTS users_referral_bonus_policy_check;

-- ALTER TABLE users ADD CONSTRAINT users_referral_bonus_policy_check CHECK (
--     referral_bonus_policy IN (
--         'default',
--         'fixed_first_payment_instant',
--         'fixed_first_payment_balance'
--     )
-- );

-- ALTER TABLE tasks
--     ADD COLUMN IF NOT EXISTS bonus_amount_kopecks BIGINT CHECK (
--         bonus_amount_kopecks IS NULL OR bonus_amount_kopecks >= 0
--     );

-- CREATE TABLE IF NOT EXISTS user_balance_ledger (
--     id BIGSERIAL PRIMARY KEY,
--     user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
--     amount_kopecks BIGINT NOT NULL CHECK (amount_kopecks <> 0),
--     kind TEXT NOT NULL,
--     referee_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     referee_payment_id BIGINT REFERENCES payments (id) ON DELETE SET NULL,
--     task_id BIGINT REFERENCES tasks (id) ON DELETE SET NULL,
--     note TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     CONSTRAINT user_balance_ledger_kind_check CHECK (
--         kind IN ('referral_first_payment')
--     )
-- );

-- CREATE UNIQUE INDEX IF NOT EXISTS uq_user_balance_ledger_referral_first_payment
--     ON user_balance_ledger (user_id, referee_id)
--     WHERE kind = 'referral_first_payment' AND referee_id IS NOT NULL;

-- CREATE INDEX IF NOT EXISTS ix_user_balance_ledger_user_id_created_at
--     ON user_balance_ledger (user_id, created_at DESC);

-- ALTER TABLE tasks
--     ADD COLUMN IF NOT EXISTS delivery_channel TEXT NOT NULL DEFAULT 'telegram';

-- ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_delivery_channel_check;

-- ALTER TABLE tasks ADD CONSTRAINT tasks_delivery_channel_check CHECK (
--     delivery_channel IN ('telegram', 'website', 'email')
-- );

-- CREATE INDEX IF NOT EXISTS idx_tasks_delivery_channel_pending
--     ON tasks (delivery_channel, status)
--     WHERE status = 'pending';

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS origin_domain TEXT;

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS cdn_domain TEXT;

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS xhttp_path TEXT NOT NULL DEFAULT '/uploadfiles/';

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS provision_step TEXT;

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS provision_progress INTEGER NOT NULL DEFAULT 0;

-- ALTER TABLE servers
--     ADD COLUMN IF NOT EXISTS provision_detail TEXT;

-- ALTER TABLE servers DROP CONSTRAINT IF EXISTS servers_provision_progress_check;

-- ALTER TABLE servers ADD CONSTRAINT servers_provision_progress_check CHECK (
--     provision_progress >= 0 AND provision_progress <= 100
-- );

-- ALTER TABLE servers DROP CONSTRAINT IF EXISTS servers_proxy_kind_check;

-- ALTER TABLE servers ADD CONSTRAINT servers_proxy_kind_check CHECK (
--     proxy_kind IN ('vless', 'vless_grpc', 'vless_ws', 'vless_xhttp', 'vless_vk_cdn_xhttp', 'hysteria2')
-- );

-- -- Полноценный финансовый контур: счета, долги, возвраты, вывод прибыли.
-- CREATE TABLE IF NOT EXISTS cash_accounts (
--     id BIGSERIAL PRIMARY KEY,
--     name TEXT NOT NULL,
--     kind TEXT NOT NULL DEFAULT 'bank',
--     currency TEXT NOT NULL DEFAULT 'RUB',
--     opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
--     opened_on DATE NOT NULL DEFAULT CURRENT_DATE,
--     active BOOLEAN NOT NULL DEFAULT TRUE,
--     is_default BOOLEAN NOT NULL DEFAULT FALSE,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     CONSTRAINT cash_accounts_kind_check CHECK (
--         kind IN ('bank', 'psp', 'cash', 'person', 'other')
--     ),
--     CONSTRAINT cash_accounts_opening_balance_check CHECK (opening_balance >= 0)
-- );

-- ALTER TABLE expenses
--     ADD COLUMN IF NOT EXISTS payment_source TEXT NOT NULL DEFAULT 'company',
--     ADD COLUMN IF NOT EXISTS paid_by_name TEXT,
--     ADD COLUMN IF NOT EXISTS cash_account_id BIGINT,
--     ADD COLUMN IF NOT EXISTS paid_on DATE;

-- ALTER TABLE expenses DROP CONSTRAINT IF EXISTS expenses_payment_source_check;

-- ALTER TABLE expenses ADD CONSTRAINT expenses_payment_source_check CHECK (
--     payment_source IN ('company', 'person', 'unpaid')
-- );

-- ALTER TABLE expenses DROP CONSTRAINT IF EXISTS expenses_cash_account_fk;

-- ALTER TABLE expenses ADD CONSTRAINT expenses_cash_account_fk
--     FOREIGN KEY (cash_account_id) REFERENCES cash_accounts (id) ON DELETE SET NULL;

-- CREATE TABLE IF NOT EXISTS cash_transactions (
--     id BIGSERIAL PRIMARY KEY,
--     account_id BIGINT NOT NULL REFERENCES cash_accounts (id) ON DELETE RESTRICT,
--     occurred_on DATE NOT NULL,
--     amount NUMERIC(14, 2) NOT NULL CHECK (amount <> 0),
--     kind TEXT NOT NULL DEFAULT 'adjustment',
--     title TEXT NOT NULL,
--     note TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     CONSTRAINT cash_transactions_kind_check CHECK (
--         kind IN ('adjustment', 'transfer_in', 'transfer_out')
--     )
-- );

-- CREATE TABLE IF NOT EXISTS payables (
--     id BIGSERIAL PRIMARY KEY,
--     counterparty_name TEXT NOT NULL,
--     title TEXT NOT NULL,
--     amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
--     paid_amount NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
--     status TEXT NOT NULL DEFAULT 'open',
--     source_type TEXT NOT NULL DEFAULT 'manual',
--     expense_id BIGINT REFERENCES expenses (id) ON DELETE SET NULL,
--     incurred_on DATE NOT NULL,
--     due_on DATE,
--     note TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     CONSTRAINT payables_status_check CHECK (status IN ('open', 'partial', 'paid', 'cancelled')),
--     CONSTRAINT payables_source_type_check CHECK (source_type IN ('manual', 'expense', 'referral', 'salary', 'other')),
--     CONSTRAINT payables_paid_not_over_amount CHECK (paid_amount <= amount)
-- );

-- CREATE TABLE IF NOT EXISTS refunds (
--     id BIGSERIAL PRIMARY KEY,
--     payment_id BIGINT REFERENCES payments (id) ON DELETE SET NULL,
--     user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     account_id BIGINT REFERENCES cash_accounts (id) ON DELETE SET NULL,
--     refunded_on DATE NOT NULL,
--     amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
--     net_amount NUMERIC(14, 2) NOT NULL CHECK (net_amount > 0),
--     status TEXT NOT NULL DEFAULT 'succeeded',
--     reason TEXT,
--     note TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     CONSTRAINT refunds_status_check CHECK (status IN ('pending', 'succeeded', 'failed', 'cancelled'))
-- );

-- CREATE TABLE IF NOT EXISTS profit_withdrawals (
--     id BIGSERIAL PRIMARY KEY,
--     account_id BIGINT REFERENCES cash_accounts (id) ON DELETE SET NULL,
--     withdrawn_on DATE NOT NULL,
--     amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
--     recipient_name TEXT NOT NULL,
--     status TEXT NOT NULL DEFAULT 'succeeded',
--     note TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
--     CONSTRAINT profit_withdrawals_status_check CHECK (
--         status IN ('planned', 'succeeded', 'cancelled')
--     )
-- );

-- CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_accounts_one_default
--     ON cash_accounts (is_default)
--     WHERE is_default = TRUE;

-- CREATE INDEX IF NOT EXISTS idx_expenses_payment_source ON expenses (payment_source);

-- CREATE INDEX IF NOT EXISTS idx_cash_transactions_account_day
--     ON cash_transactions (account_id, occurred_on DESC);

-- CREATE INDEX IF NOT EXISTS idx_payables_status ON payables (status);

-- CREATE INDEX IF NOT EXISTS idx_refunds_refunded_on ON refunds (refunded_on DESC);

-- CREATE INDEX IF NOT EXISTS idx_profit_withdrawals_withdrawn_on
--     ON profit_withdrawals (withdrawn_on DESC);

-- INSERT INTO cash_accounts (name, kind, currency, opening_balance, opened_on, active, is_default)
-- SELECT 'Расчетный счет', 'bank', 'RUB', 0, CURRENT_DATE, TRUE, TRUE
-- WHERE NOT EXISTS (SELECT 1 FROM cash_accounts WHERE is_default = TRUE);

-- Индексы для ускорения статистики (идемпотентно на существующих БД).
CREATE INDEX IF NOT EXISTS idx_payments_created_at
    ON payments (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_created_at_msk_date
    ON payments (((created_at AT TIME ZONE 'Europe/Moscow')::date));

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_date_user
    ON user_server_traffic (traffic_date, user_id);

CREATE INDEX IF NOT EXISTS idx_subscription_devices_user_created_at
    ON subscription_devices (user_id, created_at);

-- Rollup-таблицы платежей (триггер и backfill — database/rollups/pre_payments_rollup.sql).
CREATE TABLE IF NOT EXISTS stats_payments_daily_utc (
    day_utc date NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 2) NOT NULL DEFAULT 0,
    net numeric(14, 2) NOT NULL DEFAULT 0,
    cnt bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, payment_kind),
    CONSTRAINT stats_payments_daily_utc_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE TABLE IF NOT EXISTS stats_payments_daily_msk (
    day_msk date NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 2) NOT NULL DEFAULT 0,
    net numeric(14, 2) NOT NULL DEFAULT 0,
    cnt bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (day_msk, payment_kind),
    CONSTRAINT stats_payments_daily_msk_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE TABLE IF NOT EXISTS stats_payments_spread_monthly_utc (
    ym char(7) NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 6) NOT NULL DEFAULT 0,
    net numeric(14, 6) NOT NULL DEFAULT 0,
    PRIMARY KEY (ym, payment_kind),
    CONSTRAINT stats_payments_spread_monthly_utc_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE INDEX IF NOT EXISTS idx_stats_payments_daily_utc_day
    ON stats_payments_daily_utc (day_utc);

CREATE INDEX IF NOT EXISTS idx_stats_payments_daily_msk_day
    ON stats_payments_daily_msk (day_msk);
