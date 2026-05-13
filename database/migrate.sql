-- Одноразовые миграции уже применены; схема и догонка — в database/init.sql.
-- Файл оставлен: ensure_schema и docker-entrypoint-initdb.d ожидают его наличие.

-- payment_kind: убран тип manual (бывшие manual → one_time).
UPDATE payments SET payment_kind = 'one_time' WHERE payment_kind = 'manual';

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_payment_kind_check;

ALTER TABLE payments ADD CONSTRAINT payments_payment_kind_check CHECK (
    payment_kind IN ('subscription', 'one_time')
);

ALTER TABLE payments ALTER COLUMN payment_kind SET DEFAULT 'subscription';
