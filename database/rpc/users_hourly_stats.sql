-- 24 часа внутри календарного дня ``p_day`` по часовому поясу Europe/Moscow.
-- period_start_utc — начало каждого часа в Москве (как абсолютный момент времени).
-- Метрики накопительные на конец часа (все пользователи / данные строго до конца часа).
-- Пользователи без registered_at учитываются во всех часах (как в дневной сводке).

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
WITH bounds AS (
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
latest_traffic AS (
    SELECT DISTINCT ON (user_id, server_id)
        user_id,
        server_id,
        up_bytes + down_bytes AS bytes
    FROM user_server_traffic
    ORDER BY user_id, server_id, traffic_date DESC
),
user_traffic_total AS (
    SELECT
        user_id,
        COALESCE(SUM(bytes), 0)::bigint AS total_bytes
    FROM latest_traffic
    GROUP BY user_id
),
undated_users AS (
    SELECT COUNT(*)::bigint AS n FROM users WHERE registered_at IS NULL
),
undated_with_traffic AS (
    SELECT COUNT(*)::bigint AS n
    FROM users u
    LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
    WHERE u.registered_at IS NULL AND COALESCE(utt.total_bytes, 0) > 0
),
baseline AS (
    SELECT
        b.day_start,
        (
            (SELECT n FROM undated_users)
            + (
                SELECT COUNT(*)::bigint
                FROM users u
                WHERE u.registered_at IS NOT NULL
                  AND u.registered_at < b.day_start
            )
        )::bigint AS users_at_start,
        (
            (SELECT n FROM undated_with_traffic)
            + (
                SELECT COUNT(*)::bigint
                FROM users u
                LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
                WHERE u.registered_at IS NOT NULL
                  AND u.registered_at < b.day_start
                  AND COALESCE(utt.total_bytes, 0) > 0
            )
        )::bigint AS traffic_at_start,
        (
            SELECT COUNT(*)::bigint
            FROM (
                SELECT user_id, MIN(created_at) AS first_at
                FROM subscription_devices
                GROUP BY user_id
            ) fd
            WHERE fd.first_at < b.day_start
        )::bigint AS devices_at_start,
        (SELECT n FROM undated_users)::bigint AS undated_n
    FROM bounds b
)
SELECT
    h.period_start_utc,
    (
        (SELECT n FROM undated_users)
        + (
            SELECT COUNT(*)::bigint
            FROM users u
            WHERE u.registered_at IS NOT NULL
              AND u.registered_at < h.period_start_utc + interval '1 hour'
        )
    ) AS users_count,
    (
        (SELECT n FROM undated_with_traffic)
        + (
            SELECT COUNT(*)::bigint
            FROM users u
            LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
            WHERE u.registered_at IS NOT NULL
              AND u.registered_at < h.period_start_utc + interval '1 hour'
              AND COALESCE(utt.total_bytes, 0) > 0
        )
    ) AS users_with_traffic_count,
    0::bigint AS active_users_count,
    (
        SELECT COUNT(*)::bigint
        FROM (
            SELECT user_id, MIN(created_at) AS first_at
            FROM subscription_devices
            GROUP BY user_id
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
