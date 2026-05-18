-- Догонка существующих БД: external_id → tribute_webhook (полное тело webhook Tribute).

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
