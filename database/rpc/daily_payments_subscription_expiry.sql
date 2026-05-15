-- По календарным дням UTC: оплаты; окончание подписки (всего = inactive + active);
-- «active» — тот же день subscription_until и рост суммарного трафика этот день (как active_users в daily_stats).
drop function if exists rpc_daily_payments_and_subscription_expirations;

CREATE OR REPLACE FUNCTION rpc_daily_payments_and_subscription_expirations ()
RETURNS TABLE (
    stats_date date,
    payments_count bigint,
    subscriptions_expired_inactive_count bigint,
    subscriptions_expired_active_count bigint
)
LANGUAGE sql
STABLE
AS $$
WITH eligible AS (
    SELECT u.id
    FROM users u
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
),
latest_traffic AS (
    SELECT DISTINCT ON (t.user_id, t.server_id)
        t.user_id,
        t.server_id,
        t.up_bytes + t.down_bytes AS bytes
    FROM user_server_traffic t
    INNER JOIN eligible e ON e.id = t.user_id
    ORDER BY t.user_id, t.server_id, t.traffic_date DESC
),
traffic_local AS (
    SELECT
        t.user_id,
        t.server_id,
        t.traffic_date,
        t.up_bytes + t.down_bytes AS bytes,
        t.traffic_date AS local_d
    FROM user_server_traffic t
    INNER JOIN eligible e ON e.id = t.user_id
),
traffic_bounds AS (
    SELECT MIN(local_d) AS dmin, MAX(local_d) AS dmax
    FROM traffic_local
),
traffic_days AS (
    SELECT generate_series(b.dmin, b.dmax, '1 day'::interval)::date AS cal_day
    FROM traffic_bounds b
    WHERE b.dmin IS NOT NULL
      AND b.dmax IS NOT NULL
),
latest_per_day AS (
    SELECT DISTINCT ON (d.cal_day, tl.user_id, tl.server_id)
        d.cal_day,
        tl.user_id,
        tl.server_id,
        tl.bytes
    FROM traffic_days d
    INNER JOIN traffic_local tl ON tl.local_d <= d.cal_day
    ORDER BY d.cal_day, tl.user_id, tl.server_id, tl.traffic_date DESC
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
expired_active_by_day AS (
    SELECT
        w.cal_day,
        COUNT(*) FILTER (
            WHERE w.total > COALESCE(w.prev_total, 0)
        )::bigint AS n
    FROM with_prev w
    INNER JOIN users u ON u.id = w.user_id
    INNER JOIN eligible e ON e.id = u.id
    WHERE u.subscription_until = w.cal_day
    GROUP BY w.cal_day
),
pay_by_day AS (
    SELECT
        (p.created_at AT TIME ZONE 'UTC')::date AS d,
        COUNT(*)::bigint AS n
    FROM payments p
    INNER JOIN eligible e ON e.id = p.user_id
    GROUP BY 1
),
exp_by_day AS (
    SELECT
        u.subscription_until AS d,
        COUNT(*)::bigint AS n
    FROM users u
    INNER JOIN eligible e ON e.id = u.id
    GROUP BY u.subscription_until
),
key_days AS (
    SELECT d FROM pay_by_day
    UNION
    SELECT d FROM exp_by_day
    UNION
    SELECT cal_day FROM expired_active_by_day
),
bounds AS (
    SELECT MIN(d) AS d0, MAX(d) AS d1 FROM key_days
),
dense AS (
    SELECT generate_series(d0, d1, '1 day'::interval)::date AS stats_date
    FROM bounds
    WHERE d0 IS NOT NULL
      AND d1 IS NOT NULL
      AND d0 <= d1
)
SELECT
    d.stats_date,
    COALESCE(p.n, 0)::bigint AS payments_count,
    GREATEST(
        COALESCE(x.n, 0) - COALESCE(a.n, 0),
        0::bigint
    ) AS subscriptions_expired_inactive_count,
    COALESCE(a.n, 0)::bigint AS subscriptions_expired_active_count
FROM dense d
LEFT JOIN pay_by_day p ON p.d = d.stats_date
LEFT JOIN exp_by_day x ON x.d = d.stats_date
LEFT JOIN expired_active_by_day a ON a.cal_day = d.stats_date
ORDER BY d.stats_date;
$$;
