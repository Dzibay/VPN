-- Дневная сводка: registered_at, payments, devices — календарь Europe/Moscow;
-- traffic_date (снимки) — календарный день UTC на момент сбора (см. xray_stats_collect).
-- Все метрики только по пользователям с заполненными registered_at и subscription_until.
-- Календарь выдачи: от первой регистрации (МСК) до сегодня по Europe/Moscow.
-- На графике админки показывают последние 30 дней; накопительные серии считаются на фронте по полному ряду.
drop function if exists rpc_users_daily_stats;

CREATE OR REPLACE FUNCTION rpc_users_daily_stats ()
RETURNS TABLE (
    stats_date date,
    users_count bigint,
    users_with_traffic_count bigint,
    active_users_count bigint,
    subscription_devices_users_count bigint,
    users_cumulative_traffic_over_100_mbit_count bigint,
    persistent_traffic_users_count bigint,
    users_with_payment_count bigint,
    active_users_with_payment_count bigint,
    users_with_active_subscription_count bigint
)
LANGUAGE sql
STABLE
AS $$
WITH eligible_users AS (
    SELECT u.id
    FROM users u
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
),
msk_bounds AS (
    SELECT
        (NOW() AT TIME ZONE 'Europe/Moscow')::date AS msk_today,
        COALESCE(
            (
                SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
                FROM users u
                WHERE u.registered_at IS NOT NULL
                  AND u.subscription_until IS NOT NULL
            ),
            (NOW() AT TIME ZONE 'Europe/Moscow')::date
        ) AS window_start
),
-- Первый платёж (календарный день Europe/Moscow).
first_payment AS (
    SELECT
        p.user_id,
        MIN((p.created_at AT TIME ZONE 'Europe/Moscow')::date) AS first_pay_day
    FROM payments p
    INNER JOIN eligible_users eu ON eu.id = p.user_id
    GROUP BY p.user_id
),
new_payers_by_day AS (
    SELECT
        fp.first_pay_day AS pay_day,
        COUNT(*)::bigint AS users_with_payment_count
    FROM first_payment fp
    GROUP BY fp.first_pay_day
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
reg AS (
    SELECT
        (u.registered_at AT TIME ZONE 'Europe/Moscow')::date AS sd,
        COUNT(*)::bigint AS users_count,
        SUM(
            CASE WHEN COALESCE(utt.total_bytes, 0) > 0 THEN 1 ELSE 0 END
        )::bigint AS users_with_traffic_count
    FROM users u
    LEFT JOIN user_traffic_total utt ON utt.user_id = u.id
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
    GROUP BY (u.registered_at AT TIME ZONE 'Europe/Moscow')::date
),
traffic_local AS (
    SELECT
        t.user_id,
        t.server_id,
        t.traffic_date,
        t.up_bytes + t.down_bytes AS bytes,
        t.traffic_date AS local_d
    FROM user_server_traffic t
    INNER JOIN eligible_users eu ON eu.id = t.user_id
),
bounds AS (
    SELECT MIN(local_d) AS dmin, MAX(local_d) AS dmax
    FROM traffic_local
),
days AS (
    SELECT generate_series(b.dmin, b.dmax, '1 day'::interval)::date AS cal_day
    FROM bounds b
    WHERE b.dmin IS NOT NULL
      AND b.dmax IS NOT NULL
),
latest_per_day AS (
    SELECT DISTINCT ON (d.cal_day, tl.user_id, tl.server_id)
        d.cal_day,
        tl.user_id,
        tl.server_id,
        tl.bytes
    FROM days d
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
active_by_day AS (
    SELECT
        cal_day,
        COUNT(*) FILTER (
            WHERE total > COALESCE(prev_total, 0)
        )::bigint AS active_users_count
    FROM with_prev
    GROUP BY cal_day
),
active_users_with_payment_by_day AS (
    SELECT
        w.cal_day,
        COUNT(*) FILTER (
            WHERE w.total > COALESCE(w.prev_total, 0)
              AND EXISTS (
                  SELECT 1
                  FROM first_payment fp
                  WHERE fp.user_id = w.user_id
                    AND fp.first_pay_day <= w.cal_day
              )
        )::bigint AS active_users_with_payment_count
    FROM with_prev w
    GROUP BY w.cal_day
),
-- Порог объёма: 100 Мбит (десятичных, 100×10⁶ бит) → байты.
high_traffic_users_by_day AS (
    SELECT
        cal_day,
        COUNT(*) FILTER (
            WHERE total > (100::bigint * 1000000 / 8)
        )::bigint AS users_cumulative_traffic_over_100_mbit_count
    FROM user_total_by_day
    GROUP BY cal_day
),
user_active_on_day AS (
    SELECT
        cal_day,
        user_id
    FROM with_prev
    WHERE total > COALESCE(prev_total, 0)
),
first_user_active_day AS (
    SELECT user_id, MIN(cal_day) AS first_cal
    FROM user_active_on_day
    GROUP BY user_id
),
persistent_traffic_users_by_day AS (
    SELECT
        u.cal_day,
        COUNT(*)::bigint AS persistent_traffic_users_count
    FROM user_active_on_day u
    INNER JOIN first_user_active_day f
        ON f.user_id = u.user_id
       AND u.cal_day > f.first_cal
    GROUP BY u.cal_day
),
first_dev AS (
    SELECT sd.user_id, MIN(sd.created_at) AS first_at
    FROM subscription_devices sd
    INNER JOIN eligible_users eu ON eu.id = sd.user_id
    GROUP BY sd.user_id
),
dev AS (
    SELECT
        (fd.first_at AT TIME ZONE 'Europe/Moscow')::date AS sd,
        COUNT(*)::bigint AS cnt
    FROM first_dev fd
    GROUP BY 1
),
dense_calendar AS (
    SELECT generate_series(w.window_start, w.msk_today, '1 day'::interval)::date AS cal_day
    FROM msk_bounds w
),
-- Снимок на конец календарного дня Europe/Moscow: подписка активна (subscription_until >= cal_day),
-- только пользователи с известными registered_at и subscription_until.
subscription_active_by_day AS (
    SELECT
        dc.cal_day,
        COUNT(u.id)::bigint AS users_with_active_subscription_count
    FROM dense_calendar dc
    LEFT JOIN users u
        ON (u.registered_at AT TIME ZONE 'Europe/Moscow')::date <= dc.cal_day
       AND u.subscription_until >= dc.cal_day
       AND u.registered_at IS NOT NULL
       AND u.subscription_until IS NOT NULL
    GROUP BY dc.cal_day
),
merged AS (
    SELECT
        dc.cal_day AS stats_date,
        COALESCE(r.users_count, 0)::bigint AS users_count,
        COALESCE(r.users_with_traffic_count, 0)::bigint AS users_with_traffic_count,
        COALESCE(a.active_users_count, 0)::bigint AS active_users_count,
        COALESCE(d.cnt, 0)::bigint AS subscription_devices_users_count,
        COALESCE(h.users_cumulative_traffic_over_100_mbit_count, 0)::bigint
            AS users_cumulative_traffic_over_100_mbit_count,
        COALESCE(p.persistent_traffic_users_count, 0)::bigint
            AS persistent_traffic_users_count,
        COALESCE(np.users_with_payment_count, 0)::bigint AS users_with_payment_count,
        COALESCE(apay.active_users_with_payment_count, 0)::bigint
            AS active_users_with_payment_count,
        COALESCE(sub.users_with_active_subscription_count, 0)::bigint
            AS users_with_active_subscription_count
    FROM dense_calendar dc
    LEFT JOIN reg r ON r.sd = dc.cal_day
    LEFT JOIN active_by_day a ON a.cal_day = dc.cal_day
    LEFT JOIN dev d ON d.sd = dc.cal_day
    LEFT JOIN high_traffic_users_by_day h ON h.cal_day = dc.cal_day
    LEFT JOIN persistent_traffic_users_by_day p ON p.cal_day = dc.cal_day
    LEFT JOIN active_users_with_payment_by_day apay ON apay.cal_day = dc.cal_day
    LEFT JOIN new_payers_by_day np ON np.pay_day = dc.cal_day
    LEFT JOIN subscription_active_by_day sub ON sub.cal_day = dc.cal_day
),
undated AS (
    SELECT
        NULL::date AS stats_date,
        r.users_count,
        r.users_with_traffic_count,
        0::bigint AS active_users_count,
        0::bigint AS subscription_devices_users_count,
        0::bigint AS users_cumulative_traffic_over_100_mbit_count,
        0::bigint AS persistent_traffic_users_count,
        0::bigint AS users_with_payment_count,
        0::bigint AS active_users_with_payment_count,
        0::bigint AS users_with_active_subscription_count
    FROM reg r
    WHERE r.sd IS NULL
)
SELECT
    u.stats_date,
    u.users_count,
    u.users_with_traffic_count,
    u.active_users_count,
    u.subscription_devices_users_count,
    u.users_cumulative_traffic_over_100_mbit_count,
    u.persistent_traffic_users_count,
    u.users_with_payment_count,
    u.active_users_with_payment_count,
    u.users_with_active_subscription_count
FROM (
    SELECT *
    FROM merged
    UNION ALL
    SELECT *
    FROM undated
) u
ORDER BY u.stats_date NULLS LAST;
$$;
