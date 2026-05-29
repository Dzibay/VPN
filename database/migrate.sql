-- Догонка существующих БД: tribute_webhook → provider_webhook, провайдер yookassa.

-- Маршрутизация Google/YouTube на каскадном входе: exit (через exit, по умолчанию) | entry (через вход).
ALTER TABLE servers ADD COLUMN IF NOT EXISTS google_routing_mode TEXT NOT NULL DEFAULT 'exit';

ALTER TABLE servers DROP CONSTRAINT IF EXISTS servers_google_routing_mode_check;
ALTER TABLE servers ADD CONSTRAINT servers_google_routing_mode_check
    CHECK (google_routing_mode IN ('exit', 'entry'));

