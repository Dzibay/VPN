-- Догонка существующих БД: tribute_webhook → provider_webhook, провайдер yookassa.

-- Чистая сумма после комиссии PSP (ЮKassa income_amount; Tribute −10%; manual = amount).
ALTER TABLE payments ADD COLUMN IF NOT EXISTS net_amount NUMERIC(14, 2);

UPDATE payments
SET net_amount = (provider_webhook #>> '{object,income_amount,value}')::numeric(14, 2)
WHERE net_amount IS NULL
  AND provider = 'yookassa'
  AND provider_webhook #>> '{object,income_amount,value}' ~ '^[0-9]+(\.[0-9]+)?$';

UPDATE payments
SET net_amount = ROUND(amount * 0.90, 2)
WHERE net_amount IS NULL
  AND provider = 'tribute';

UPDATE payments
SET net_amount = amount
WHERE net_amount IS NULL;

ALTER TABLE payments ALTER COLUMN net_amount SET NOT NULL;


