-- 24 часа внутри календарного дня ``p_day`` по часовому поясу Europe/Moscow.
-- period_start_utc — начало каждого часа в Москве (как абсолютный момент времени).
-- Метрики накопительные на конец часа (все пользователи / данные строго до конца часа).
-- Накопление users_count: учётные пользователи (Telegram или подтверждённый email).
-- Прочие почасовые метрики устройств/трафика — только с registered_at и subscription_until.

CREATE OR REPLACE FUNCTION rpc_users_hourly_stats (p_day date)
RETURNS TABLE (
    period_start_utc timestamptz,
    users_count bigint,
    users_with_traffic_count bigint,
    active_users_count bigint,
    subscription_devices_users_count bigint,
    baseline_users_count bigint,
    baseline_users_with_traffic_count bigint,
    baseline_subscription_devices_users_count bigint,
    undated_users_count bigint
)
LANGUAGE sql
STABLE
AS $$
WITH qualified_users AS (
    SELECT u.id
    FROM users u
    WHERE u.telegram_id IS NOT NULL
       OR (
           u.email IS NOT NULL
           AND BTRIM(u.email) <> ''
           AND u.email_verified_at IS NOT NULL
       )
),
bounds AS (
    SELECT (p_day::timestamp AT TIME ZONE 'Europe/Moscow') AS day_start
),
hours AS (
    SELECT generate_series(
        b.day_start,
        b.day_start + interval '23 hours',
        interval '1 hour'
    ) AS period_start_utc
    FROM bounds b
),
eligible_users AS (
    SELECT u.id
    FROM users u
    INNER JOIN qualified_users qu ON qu.id = u.id
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
),
latest_traffic AS (
    SELECT DISTINCT ON (t.user_id, t.server_id)
        t.user_id,
        t.server_id,
        t.up_bytes + t.down_bytes AS bytes
    FROM user_server_traffic t
    INNER JOIN eligible_users eu ON eu.id = t.user_id
    ORDER BY t.user_id, t.server_id, t.traffic_date DESC
),
user_traffic_total AS (
    SELECT
        user_id,
        COALESCE(SUM(bytes), 0)::bigint AS total_bytes
    FROM latest_traffic
    GROUP BY user_id
),
latest_traffic_all AS (
    SELECT DISTINCT ON (t.user_id, t.server_id)
        t.user_id,
        t.server_id,
        t.up_bytes + t.down_bytes AS bytes
    FROM user_server_traffic t
    INNER JOIN qualified_users qu ON qu.id = t.user_id
    ORDER BY t.user_id, t.server_id, t.traffic_date DESC
),
user_traffic_total_all AS (
    SELECT
        user_id,
        COALESCE(SUM(bytes), 0)::bigint AS total_bytes
    FROM latest_traffic_all
    GROUP BY user_id
),
baseline AS (
    SELECT
        b.day_start,
        (
            SELECT COUNT(*)::bigint
            FROM users u
            INNER JOIN qualified_users qu ON qu.id = u.id
            WHERE u.registered_at IS NULL
               OR u.registered_at < b.day_start
        )::bigint AS users_at_start,
        (
            SELECT COUNT(*)::bigint
            FROM users u
            INNER JOIN qualified_users qu ON qu.id = u.id
            LEFT JOIN user_traffic_total_all utt ON utt.user_id = u.id
            WHERE (u.registered_at IS NULL OR u.registered_at < b.day_start)
              AND COALESCE(utt.total_bytes, 0) > 0
        )::bigint AS traffic_at_start,
        (
            SELECT COUNT(*)::bigint
            FROM (
                SELECT sd.user_id, MIN(sd.created_at) AS first_at
                FROM subscription_devices sd
                INNER JOIN eligible_users eu ON eu.id = sd.user_id
                GROUP BY sd.user_id
            ) fd
            WHERE fd.first_at < b.day_start
        )::bigint AS devices_at_start,
        (
            SELECT COUNT(*)::bigint
            FROM users u
            INNER JOIN qualified_users qu ON qu.id = u.id
            WHERE u.registered_at IS NULL
        )::bigint AS undated_n
    FROM bounds b
)
SELECT
    h.period_start_utc,
    (
        SELECT COUNT(*)::bigint
        FROM users u
        INNER JOIN qualified_users qu ON qu.id = u.id
        WHERE u.registered_at IS NULL
           OR u.registered_at < h.period_start_utc + interval '1 hour'
    ) AS users_count,
    (
        SELECT COUNT(*)::bigint
        FROM users u
        INNER JOIN qualified_users qu ON qu.id = u.id
        LEFT JOIN user_traffic_total_all utt ON utt.user_id = u.id
        WHERE (u.registered_at IS NULL OR u.registered_at < h.period_start_utc + interval '1 hour')
          AND COALESCE(utt.total_bytes, 0) > 0
    ) AS users_with_traffic_count,
    0::bigint AS active_users_count,
    (
        SELECT COUNT(*)::bigint
        FROM (
            SELECT sd.user_id, MIN(sd.created_at) AS first_at
            FROM subscription_devices sd
            INNER JOIN eligible_users eu ON eu.id = sd.user_id
            GROUP BY sd.user_id
        ) fd
        WHERE fd.first_at < h.period_start_utc + interval '1 hour'
    ) AS subscription_devices_users_count,
    bl.users_at_start AS baseline_users_count,
    bl.traffic_at_start AS baseline_users_with_traffic_count,
    bl.devices_at_start AS baseline_subscription_devices_users_count,
    bl.undated_n AS undated_users_count
FROM hours h
CROSS JOIN baseline bl
ORDER BY h.period_start_utc;
$$;
