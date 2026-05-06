DROP FUNCTION IF EXISTS rpc_users_hourly_stats (date);
DROP FUNCTION IF EXISTS rpc_users_hourly_stats (date, text);

-- 24 часа UTC внутри календарного дня ``p_day`` (UTC).
-- users_count / users_with_traffic_count / subscription_devices_users_count —
-- накопительные значения на конец каждого часа (учитываются все данные до этого момента, не только выбранный день).

CREATE OR REPLACE FUNCTION rpc_users_hourly_stats (p_day date)
RETURNS TABLE (
    period_start_utc timestamptz,
    users_count bigint,
    users_with_traffic_count bigint,
    active_users_count bigint,
    subscription_devices_users_count bigint
)
LANGUAGE sql
STABLE
AS $$
WITH bounds AS (
    SELECT ((p_day::timestamp AT TIME ZONE 'UTC')) AS day_start
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
)
SELECT
    h.period_start_utc,
    (
        SELECT COUNT(*)::bigint
        FROM users u
        WHERE u.registered_at IS NOT NULL
          AND u.registered_at < h.period_start_utc + interval '1 hour'
    ) AS users_count,
    (
        SELECT COUNT(*)::bigint
        FROM users u
        LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
        WHERE u.registered_at IS NOT NULL
          AND u.registered_at < h.period_start_utc + interval '1 hour'
          AND COALESCE(utt.total_bytes, 0) > 0
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
    ) AS subscription_devices_users_count
FROM hours h
ORDER BY h.period_start_utc;
$$;
