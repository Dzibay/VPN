-- Догонка существующих БД: tribute_webhook → provider_webhook, провайдер yookassa.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payments'
          AND column_name = 'tribute_webhook'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payments'
          AND column_name = 'provider_webhook'
    ) THEN
        ALTER TABLE payments RENAME COLUMN tribute_webhook TO provider_webhook;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payments'
          AND column_name = 'provider_webhook'
    ) THEN
        ALTER TABLE payments ADD COLUMN provider_webhook JSONB;
    END IF;
END $$;

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_provider_check;

ALTER TABLE payments
    ADD CONSTRAINT payments_provider_check CHECK (provider IN ('manual', 'tribute', 'yookassa'));

-- Идемпотентность ЮKassa (только после появления колонки provider_webhook).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payments'
          AND column_name = 'provider_webhook'
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_yookassa_object_id
            ON payments ((provider_webhook #>> '{object,id}'))
            WHERE provider = 'yookassa'
              AND (provider_webhook #>> '{object,id}') IS NOT NULL;
    END IF;
END $$;
