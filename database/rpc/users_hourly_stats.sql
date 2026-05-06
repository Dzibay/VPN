DROP FUNCTION IF EXISTS rpc_users_hourly_stats ();

-- RPC: почасовая сводка UTC только за один календарный день UTC (p_day): ровно 24 строки (часы 0–23).
-- Регистрации и первые subscription_devices — по часу UTC внутри этого дня.
-- users_with_traffic_count — среди зарегистрировавшихся в этом часу этого дня (последний снимок на узел).
-- active_users_count — 0. Строк «без даты регистрации» нет.

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
    SELECT (p_day::timestamp AT TIME ZONE 'UTC') AS day_start
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
reg AS (
    SELECT
        date_trunc('hour', timezone('UTC', u.registered_at)) AS ph,
        COUNT(*)::bigint AS users_count,
        SUM(
            CASE WHEN COALESCE(utt.total_bytes, 0) > 0 THEN 1 ELSE 0 END
        )::bigint AS users_with_traffic_count
    FROM users u
    LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
    WHERE u.registered_at IS NOT NULL
      AND (timezone('UTC', u.registered_at))::date = p_day
    GROUP BY date_trunc('hour', timezone('UTC', u.registered_at))
),
first_dev AS (
    SELECT user_id, MIN(created_at) AS first_at
    FROM subscription_devices
    GROUP BY user_id
),
dev AS (
    SELECT
        date_trunc('hour', timezone('UTC', fd.first_at)) AS ph,
        COUNT(*)::bigint AS cnt
    FROM first_dev fd
    WHERE (timezone('UTC', fd.first_at))::date = p_day
    GROUP BY date_trunc('hour', timezone('UTC', fd.first_at))
)
SELECT
    h.period_start_utc,
    COALESCE(r.users_count, 0)::bigint AS users_count,
    COALESCE(r.users_with_traffic_count, 0)::bigint AS users_with_traffic_count,
    0::bigint AS active_users_count,
    COALESCE(d.cnt, 0)::bigint AS subscription_devices_users_count
FROM hours h
LEFT JOIN reg r ON r.ph = h.period_start_utc
LEFT JOIN dev d ON d.ph = h.period_start_utc
ORDER BY h.period_start_utc;
$$;
