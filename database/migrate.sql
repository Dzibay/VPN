-- Догонка существующих БД: external_id → tribute_webhook (полное тело webhook Tribute).

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_months_check;

ALTER TABLE payments ADD CONSTRAINT payments_months_check CHECK (months >= 0);

DROP TABLE IF EXISTS tribute_webhook_logs;

ALTER TABLE payments DROP COLUMN IF EXISTS external_id;

ALTER TABLE payments ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE payments ADD COLUMN IF NOT EXISTS tribute_webhook JSONB;

DROP INDEX IF EXISTS uq_payments_tribute_purchase;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tribute_digital_purchase
    ON payments ((tribute_webhook->'payload'->>'purchase_id'))
    WHERE provider = 'tribute'
        AND tribute_webhook->>'name' = 'new_digital_product'
        AND tribute_webhook->'payload'->>'purchase_id' IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tribute_subscription_period
    ON payments (
        (tribute_webhook->'payload'->>'subscription_id'),
        (tribute_webhook->'payload'->>'expires_at')
    )
    WHERE provider = 'tribute'
        AND tribute_webhook->>'name' IN ('new_subscription', 'renewed_subscription')
        AND tribute_webhook->'payload'->>'subscription_id' IS NOT NULL
        AND tribute_webhook->'payload'->>'expires_at' IS NOT NULL;

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_type_check;

ALTER TABLE tasks ADD CONSTRAINT tasks_type_check CHECK (
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
        'notify_reg_1h_no_traffic'
    )
);

-- servers: Auto-группа в подписке и скрытые узлы (не в /sub, в админке по умолчанию скрыты)
ALTER TABLE servers ADD COLUMN IF NOT EXISTS include_in_auto BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;

-- users: персональный лимит трафика (NULL = без лимита). Полный backfill — migrate_traffic_limit_bytes.sql
ALTER TABLE users DROP COLUMN IF EXISTS trial_traffic_limit_exceeded;

ALTER TABLE users ADD COLUMN IF NOT EXISTS traffic_limit_bytes BIGINT NULL;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_traffic_limit_bytes_check;

ALTER TABLE users ADD CONSTRAINT users_traffic_limit_bytes_check CHECK (
    traffic_limit_bytes IS NULL OR traffic_limit_bytes >= 0
);
