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

-- Оповещения по лимиту трафика (notify_traffic_low / notify_traffic_over).
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_type_check;

ALTER TABLE tasks
    ADD CONSTRAINT tasks_type_check CHECK (
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
    );
