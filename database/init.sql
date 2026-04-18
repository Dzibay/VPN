-- Клиенты VPN-сервиса (учётные записи, привязка к Telegram, подписка, токен доступа)
-- telegram_id: логин или произвольная строка. Пусто в БД = NULL, таких записей может быть несколько.
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT,
    subscription_until DATE,
    token TEXT NOT NULL,
    CONSTRAINT users_token_key UNIQUE (token)
);

-- Уникальность только для непустых telegram_id (несколько NULL допустимо)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)
    WHERE telegram_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_subscription_until ON users (subscription_until);
