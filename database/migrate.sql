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

-- Служебный узел id=0: архив трафика с удалённых серверов (см. traffic_archive.py).
INSERT INTO servers (
    id,
    name,
    host,
    port,
    country,
    load_percent,
    is_active,
    whitelist,
    include_in_auto,
    is_hidden,
    provision_ready,
    provision_status,
    proxy_kind,
    vless_uuid,
    reality_short_id,
    reality_dest,
    reality_server_names,
    reality_fingerprint,
    reality_spider_x,
    vless_flow,
    is_cascade_ru_entry
)
SELECT
    0,
    'Архив (удалённые узлы)',
    '__traffic_archive__',
    1,
    '',
    0,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    FALSE,
    'idle',
    'vless',
    '00000000-0000-0000-0000-000000000001',
    '00000000',
    'www.amazon.com:443',
    'www.amazon.com,amazon.com',
    'chrome',
    '/',
    'xtls-rprx-vision',
    FALSE
WHERE NOT EXISTS (SELECT 1 FROM servers WHERE id = 0);

-- Следующий id для новых узлов — не меньше 1, чтобы не пересечься с архивом.
SELECT setval(
    pg_get_serial_sequence('servers', 'id'),
    (SELECT COALESCE(MAX(id), 0) FROM servers WHERE id > 0),
    TRUE
);

