-- Бонус за досрочную оплату подписки (отдельно от реферального bonus_days).
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS early_payment_bonus_days INTEGER
    CHECK (early_payment_bonus_days IS NULL OR early_payment_bonus_days >= 0);

-- Индивидуальные условия реферальных бонусов для владельца ссылки (реферера).
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_bonus_policy TEXT NOT NULL DEFAULT 'default';

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_referral_bonus_policy_check;
ALTER TABLE users ADD CONSTRAINT users_referral_bonus_policy_check CHECK (
    referral_bonus_policy IN ('default', 'fixed_first_payment_instant')
);

-- Флаг: бонусные дни из notify_ref_pay уже зачислены на subscription_until (мгновенная политика).
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS referral_bonus_applied BOOLEAN NOT NULL DEFAULT FALSE;

-- Догонка существующих БД: tribute_webhook → provider_webhook, провайдер yookassa.

-- Маршрутизация Google/YouTube на каскадном входе: exit (через exit, по умолчанию) | entry (через вход).
ALTER TABLE servers ADD COLUMN IF NOT EXISTS google_routing_mode TEXT NOT NULL DEFAULT 'exit';

ALTER TABLE servers DROP CONSTRAINT IF EXISTS servers_google_routing_mode_check;
ALTER TABLE servers ADD CONSTRAINT servers_google_routing_mode_check
    CHECK (google_routing_mode IN ('exit', 'entry'));

-- ---------------------------------------------------------------------------
-- Идемпотентность платежей: защита от двойного зачисления при гонке webhook.
--
-- Уникальный ключ провайдера лежит внутри provider_webhook (JSONB), поэтому
-- используются частичные уникальные индексы по выражению. App-level dedup в
-- payment_service.find_duplicate_payment_id остаётся как быстрый путь; эти
-- индексы ловят гонку (два webhook одновременно проходят проверку до INSERT)
-- через IntegrityError в ingest_provider_payment.
--
-- Если в БД уже есть дубликаты — индекс НЕ создаётся (RAISE WARNING вместо
-- ошибки), чтобы не падал старт приложения; дубликаты нужно почистить вручную.
-- ---------------------------------------------------------------------------

-- ЮKassa: object.id уникален в рамках провайдера.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM payments
        WHERE provider = 'yookassa'
          AND provider_webhook -> 'object' ->> 'id' IS NOT NULL
        GROUP BY provider_webhook -> 'object' ->> 'id'
        HAVING COUNT(*) > 1
    ) THEN
        RAISE WARNING 'uq_payments_yookassa_object_id: найдены дубликаты, индекс не создан (почистите payments)';
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_yookassa_object_id
            ON payments ((provider_webhook -> 'object' ->> 'id'))
            WHERE provider = 'yookassa'
              AND provider_webhook -> 'object' ->> 'id' IS NOT NULL;
    END IF;
END $$;

-- Tribute: цифровой товар (new_digital_product) — purchase_id.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM payments
        WHERE provider = 'tribute'
          AND provider_webhook ->> 'name' = 'new_digital_product'
          AND provider_webhook -> 'payload' ->> 'purchase_id' IS NOT NULL
        GROUP BY provider_webhook -> 'payload' ->> 'purchase_id'
        HAVING COUNT(*) > 1
    ) THEN
        RAISE WARNING 'uq_payments_tribute_purchase_id: найдены дубликаты, индекс не создан (почистите payments)';
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tribute_purchase_id
            ON payments ((provider_webhook -> 'payload' ->> 'purchase_id'))
            WHERE provider = 'tribute'
              AND provider_webhook ->> 'name' = 'new_digital_product'
              AND provider_webhook -> 'payload' ->> 'purchase_id' IS NOT NULL;
    END IF;
END $$;

-- Tribute: подписка (new_subscription / renewed_subscription) — subscription_id + expires_at.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM payments
        WHERE provider = 'tribute'
          AND provider_webhook ->> 'name' IN ('new_subscription', 'renewed_subscription')
          AND provider_webhook -> 'payload' ->> 'subscription_id' IS NOT NULL
          AND provider_webhook -> 'payload' ->> 'expires_at' IS NOT NULL
        GROUP BY
            provider_webhook -> 'payload' ->> 'subscription_id',
            provider_webhook -> 'payload' ->> 'expires_at'
        HAVING COUNT(*) > 1
    ) THEN
        RAISE WARNING 'uq_payments_tribute_subscription: найдены дубликаты, индекс не создан (почистите payments)';
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tribute_subscription
            ON payments (
                (provider_webhook -> 'payload' ->> 'subscription_id'),
                (provider_webhook -> 'payload' ->> 'expires_at')
            )
            WHERE provider = 'tribute'
              AND provider_webhook ->> 'name' IN ('new_subscription', 'renewed_subscription')
              AND provider_webhook -> 'payload' ->> 'subscription_id' IS NOT NULL
              AND provider_webhook -> 'payload' ->> 'expires_at' IS NOT NULL;
    END IF;
END $$;

-- Чат поддержки в личном кабинете.
CREATE TABLE IF NOT EXISTS support_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    author_kind TEXT NOT NULL,
    body TEXT NOT NULL,
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

ALTER TABLE support_messages
    ADD COLUMN IF NOT EXISTS staff_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_support_messages_staff_user_id
    ON support_messages (staff_user_id)
    WHERE staff_user_id IS NOT NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS support_seen_at TIMESTAMPTZ;

ALTER TABLE user_http_request_traces
    ADD COLUMN IF NOT EXISTS client_ip TEXT;

CREATE TABLE IF NOT EXISTS blocked_ips (
    id BIGSERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT blocked_ips_ip_key UNIQUE (ip)
);

-- Подтверждение email при регистрации и привязке с Telegram.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

UPDATE users
SET email_verified_at = COALESCE(registered_at, NOW())
WHERE email IS NOT NULL
  AND trim(email) <> ''
  AND email_verified_at IS NULL;

-- SEO-страницы: учёт переходов для админки.
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
    ('/vpn-dlya-youtube/pc', 'VPN для YouTube на ПК', 12),
    ('/vpn-dlya-gemini', 'VPN для Gemini', 20),
    ('/vpn-dlya-telegram', 'VPN для Telegram', 30),
    ('/vpn-dlya-iphone', 'VPN для iPhone', 40),
    ('/vpn-dlya-android', 'VPN для Android', 41)
ON CONFLICT (path) DO NOTHING;

DELETE FROM seo_pages
WHERE path NOT IN (
    '/',
    '/vpn-dlya-youtube',
    '/vpn-dlya-youtube/android',
    '/vpn-dlya-youtube/pc',
    '/vpn-dlya-gemini',
    '/vpn-dlya-telegram',
    '/vpn-dlya-iphone',
    '/vpn-dlya-android'
);
