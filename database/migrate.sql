-- Одноразовые миграции уже применены; схема и догонка — в database/init.sql.
-- Файл оставлен: ensure_schema и docker-entrypoint-initdb.d ожидают его наличие.

ALTER TABLE servers ADD COLUMN IF NOT EXISTS include_in_auto BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;

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
        'notify_sub_expired_7d'
    )
);

