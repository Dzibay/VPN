-- Миграция для существующих инстансов: баланс и политика fixed_first_payment_balance.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS referral_fixed_bonus_kopecks BIGINT CHECK (
        referral_fixed_bonus_kopecks IS NULL OR referral_fixed_bonus_kopecks >= 100
    );

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS balance_kopecks BIGINT NOT NULL DEFAULT 0 CHECK (balance_kopecks >= 0);

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_referral_bonus_policy_check;

ALTER TABLE users ADD CONSTRAINT users_referral_bonus_policy_check CHECK (
    referral_bonus_policy IN (
        'default',
        'fixed_first_payment_instant',
        'fixed_first_payment_balance'
    )
);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS bonus_amount_kopecks BIGINT CHECK (
        bonus_amount_kopecks IS NULL OR bonus_amount_kopecks >= 0
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
