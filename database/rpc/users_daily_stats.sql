-- RPC: дневная сводка UTC для /api/users/daily-stats (регистрации, трафик, активные, первые устройства).
-- Логика совпадает с прежним Python (daily_stats.py): «активный» = суммарный накопленный трафик по всем узлам
-- вырос относительно предыдущего календарного дня (последний снимок на узел с traffic_date <= день).

CREATE OR REPLACE FUNCTION rpc_users_daily_stats ()
RETURNS TABLE (
    stats_date date,
    users_count bigint,
    users_with_traffic_count bigint,
    active_users_count bigint,
    subscription_devices_users_count bigint
)
LANGUAGE sql
STABLE
AS $$
WITH latest_traffic AS (
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
        (timezone('UTC', u.registered_at))::date AS sd,
        COUNT(*)::bigint AS users_count,
        SUM(
            CASE WHEN COALESCE(utt.total_bytes, 0) > 0 THEN 1 ELSE 0 END
        )::bigint AS users_with_traffic_count
    FROM users u
    LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
    GROUP BY (timezone('UTC', u.registered_at))::date
),
bounds AS (
    SELECT
        MIN(traffic_date)::date AS dmin,
        MAX(traffic_date)::date AS dmax
    FROM user_server_traffic
),
days AS (
    SELECT day::date AS cal_day
    FROM bounds b,
        LATERAL generate_series(b.dmin, b.dmax, '1 day'::interval) AS day
    WHERE b.dmin IS NOT NULL
      AND b.dmax IS NOT NULL
),
latest_per_day AS (
    SELECT DISTINCT ON (d.cal_day, t.user_id, t.server_id)
        d.cal_day,
        t.user_id,
        t.server_id,
        t.up_bytes + t.down_bytes AS bytes
    FROM days d
    INNER JOIN user_server_traffic t ON t.traffic_date <= d.cal_day
    ORDER BY d.cal_day, t.user_id, t.server_id, t.traffic_date DESC
),
user_total_by_day AS (
    SELECT cal_day, user_id, SUM(bytes)::bigint AS total
    FROM latest_per_day
    GROUP BY cal_day, user_id
),
with_prev AS (
    SELECT
        cal_day,
        user_id,
        total,
        LAG(total) OVER (
            PARTITION BY user_id
            ORDER BY cal_day
        ) AS prev_total
    FROM user_total_by_day
),
active_by_day AS (
    SELECT
        cal_day,
        COUNT(*) FILTER (
            WHERE total > COALESCE(prev_total, 0)
        )::bigint AS active_users_count
    FROM with_prev
    GROUP BY cal_day
),
first_dev AS (
    SELECT user_id, MIN(created_at) AS first_at
    FROM subscription_devices
    GROUP BY user_id
),
dev AS (
    SELECT
        (timezone('UTC', first_at))::date AS sd,
        COUNT(*)::bigint AS cnt
    FROM first_dev
    GROUP BY 1
),
dated_keys AS (
    SELECT sd AS dk FROM reg WHERE sd IS NOT NULL
    UNION
    SELECT cal_day FROM active_by_day
    UNION
    SELECT sd FROM dev WHERE sd IS NOT NULL
),
merged AS (
    SELECT
        dk.dk AS stats_date,
        COALESCE(r.users_count, 0)::bigint AS users_count,
        COALESCE(r.users_with_traffic_count, 0)::bigint AS users_with_traffic_count,
        COALESCE(a.active_users_count, 0)::bigint AS active_users_count,
        COALESCE(d.cnt, 0)::bigint AS subscription_devices_users_count
    FROM dated_keys dk
    LEFT JOIN reg r ON r.sd = dk.dk
    LEFT JOIN active_by_day a ON a.cal_day = dk.dk
    LEFT JOIN dev d ON d.sd = dk.dk
),
undated AS (
    SELECT
        NULL::date AS stats_date,
        r.users_count,
        r.users_with_traffic_count,
        0::bigint AS active_users_count,
        0::bigint AS subscription_devices_users_count
    FROM reg r
    WHERE r.sd IS NULL
)
SELECT
    u.stats_date,
    u.users_count,
    u.users_with_traffic_count,
    u.active_users_count,
    u.subscription_devices_users_count
FROM (
    SELECT *
    FROM merged
    UNION ALL
    SELECT *
    FROM undated
) u
ORDER BY u.stats_date NULLS LAST;
$$;
