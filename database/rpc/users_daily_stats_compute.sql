-- Тяжёлый расчёт дневной статистики пользователей (МСК). Источник для materialized view.
CREATE OR REPLACE FUNCTION fn_users_daily_stats_compute (
    p_from date DEFAULT NULL,
    p_to date DEFAULT NULL
)
RETURNS TABLE (
    stats_date date,
    users_count bigint,
    users_with_traffic_count bigint,
    active_users_count bigint,
    subscription_devices_users_count bigint,
    users_cumulative_traffic_over_100_mbit_count bigint,
    persistent_traffic_users_count bigint,
    users_with_payment_count bigint,
    payments_first_count bigint,
    payments_repeat_count bigint,
    active_users_with_payment_count bigint,
    users_with_active_subscription_count bigint
)
LANGUAGE sql
STABLE
SET search_path TO public
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
eligible_users AS (
    SELECT u.id
    FROM users u
    INNER JOIN qualified_users qu ON qu.id = u.id
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
                INNER JOIN qualified_users qu ON qu.id = u.id
                WHERE u.registered_at IS NOT NULL
            ),
            (NOW() AT TIME ZONE 'Europe/Moscow')::date
        ) AS window_start
),
date_window AS (
    SELECT
        COALESCE(p_from, mb.window_start) AS range_start,
        COALESCE(p_to, mb.msk_today) AS range_end,
        COALESCE(p_from, mb.window_start) - 1 AS traffic_lag_start
    FROM msk_bounds mb
),
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
    INNER JOIN date_window dw ON fp.first_pay_day BETWEEN dw.range_start AND dw.range_end
    GROUP BY fp.first_pay_day
),
pay_split AS (
    SELECT
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS d,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id ORDER BY p.created_at ASC, p.id ASC
        ) AS payment_num
    FROM payments p
    INNER JOIN eligible_users eu ON eu.id = p.user_id
),
payments_by_day AS (
    SELECT
        d,
        COUNT(*) FILTER (WHERE payment_num = 1)::bigint AS payments_first_count,
        COUNT(*) FILTER (WHERE payment_num > 1)::bigint AS payments_repeat_count
    FROM pay_split
    INNER JOIN date_window dw ON pay_split.d BETWEEN dw.range_start AND dw.range_end
    GROUP BY d
),
latest_traffic_all AS (
    SELECT DISTINCT ON (t.user_id, t.server_id)
        t.user_id,
        t.server_id,
        t.up_bytes + t.down_bytes AS bytes
    FROM user_server_traffic t
    ORDER BY t.user_id, t.server_id, t.traffic_date DESC
),
user_traffic_total_all AS (
    SELECT
        user_id,
        COALESCE(SUM(bytes), 0)::bigint AS total_bytes
    FROM latest_traffic_all
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
    INNER JOIN qualified_users qu ON qu.id = u.id
    LEFT JOIN user_traffic_total_all utt ON utt.user_id = u.id
    WHERE u.registered_at IS NOT NULL
    GROUP BY (u.registered_at AT TIME ZONE 'Europe/Moscow')::date
),
traffic_snapshots AS (
    SELECT
        t.user_id,
        t.server_id,
        t.traffic_date AS snap_day,
        (t.up_bytes + t.down_bytes)::bigint AS bytes
    FROM user_server_traffic t
    INNER JOIN eligible_users eu ON eu.id = t.user_id
),
traffic_ranges AS (
    SELECT
        ts.user_id,
        ts.server_id,
        ts.snap_day AS from_day,
        ts.bytes,
        LEAD(ts.snap_day) OVER (
            PARTITION BY ts.user_id, ts.server_id
            ORDER BY ts.snap_day
        ) AS next_snap_day
    FROM traffic_snapshots ts
),
traffic_filled AS (
    SELECT
        gs.cal_day::date AS cal_day,
        tr.user_id,
        tr.server_id,
        tr.bytes
    FROM traffic_ranges tr
    CROSS JOIN date_window dw
    CROSS JOIN LATERAL generate_series(
        GREATEST(tr.from_day, dw.traffic_lag_start),
        LEAST(
            COALESCE(tr.next_snap_day - 1, dw.range_end),
            dw.range_end
        ),
        interval '1 day'
    ) AS gs (cal_day)
    WHERE tr.from_day <= dw.range_end
      AND COALESCE(tr.next_snap_day - 1, dw.range_end) >= dw.traffic_lag_start
),
user_total_by_day AS (
    SELECT cal_day, user_id, SUM(bytes)::bigint AS total
    FROM traffic_filled
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
        w.cal_day,
        COUNT(*) FILTER (
            WHERE w.total > COALESCE(w.prev_total, 0)
        )::bigint AS active_users_count
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    GROUP BY w.cal_day
),
active_users_with_payment_by_day AS (
    SELECT
        w.cal_day,
        COUNT(*) FILTER (
            WHERE w.total > COALESCE(w.prev_total, 0)
              AND fp.user_id IS NOT NULL
        )::bigint AS active_users_with_payment_count
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    LEFT JOIN first_payment fp
        ON fp.user_id = w.user_id
       AND fp.first_pay_day <= w.cal_day
    GROUP BY w.cal_day
),
high_traffic_users_by_day AS (
    SELECT
        w.cal_day,
        COUNT(*) FILTER (
            WHERE w.total > (100::bigint * 1000000 / 8)
        )::bigint AS users_cumulative_traffic_over_100_mbit_count
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    GROUP BY w.cal_day
),
user_active_on_day AS (
    SELECT
        w.cal_day,
        w.user_id
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    WHERE w.total > COALESCE(w.prev_total, 0)
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
    INNER JOIN date_window dw
        ON (fd.first_at AT TIME ZONE 'Europe/Moscow')::date
           BETWEEN dw.range_start AND dw.range_end
    GROUP BY 1
),
dense_calendar AS (
    SELECT generate_series(dw.range_start, dw.range_end, '1 day'::interval)::date AS cal_day
    FROM date_window dw
),
sub_starts AS (
    SELECT
        (u.registered_at AT TIME ZONE 'Europe/Moscow')::date AS d,
        COUNT(*)::bigint AS delta
    FROM users u
    INNER JOIN qualified_users qu ON qu.id = u.id
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
    GROUP BY 1
),
sub_ends AS (
    SELECT
        (u.subscription_until::date + 1) AS d,
        (-COUNT(*))::bigint AS delta
    FROM users u
    INNER JOIN qualified_users qu ON qu.id = u.id
    WHERE u.registered_at IS NOT NULL
      AND u.subscription_until IS NOT NULL
    GROUP BY 1
),
sub_deltas AS (
    SELECT d, SUM(delta)::bigint AS delta
    FROM (
        SELECT d, delta FROM sub_starts
        UNION ALL
        SELECT d, delta FROM sub_ends
    ) x
    GROUP BY d
),
sub_cumulative AS (
    SELECT
        d,
        SUM(delta) OVER (ORDER BY d) AS running
    FROM sub_deltas
),
subscription_active_by_day AS (
    SELECT
        dc.cal_day,
        COALESCE(
            (
                SELECT sc.running
                FROM sub_cumulative sc
                WHERE sc.d <= dc.cal_day
                ORDER BY sc.d DESC
                LIMIT 1
            ),
            0
        )::bigint AS users_with_active_subscription_count
    FROM dense_calendar dc
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
        COALESCE(pb.payments_first_count, 0)::bigint AS payments_first_count,
        COALESCE(pb.payments_repeat_count, 0)::bigint AS payments_repeat_count,
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
    LEFT JOIN payments_by_day pb ON pb.d = dc.cal_day
    LEFT JOIN subscription_active_by_day sub ON sub.cal_day = dc.cal_day
),
undated AS (
    SELECT
        NULL::date AS stats_date,
        cnt.users_count,
        cnt.users_with_traffic_count,
        0::bigint AS active_users_count,
        0::bigint AS subscription_devices_users_count,
        0::bigint AS users_cumulative_traffic_over_100_mbit_count,
        0::bigint AS persistent_traffic_users_count,
        0::bigint AS users_with_payment_count,
        0::bigint AS payments_first_count,
        0::bigint AS payments_repeat_count,
        0::bigint AS active_users_with_payment_count,
        0::bigint AS users_with_active_subscription_count
    FROM (
        SELECT
            COUNT(*)::bigint AS users_count,
            SUM(
                CASE WHEN COALESCE(utt.total_bytes, 0) > 0 THEN 1 ELSE 0 END
            )::bigint AS users_with_traffic_count
        FROM users u
        INNER JOIN qualified_users qu ON qu.id = u.id
        LEFT JOIN user_traffic_total_all utt ON utt.user_id = u.id
        WHERE u.registered_at IS NULL
    ) cnt
    WHERE cnt.users_count > 0
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
    u.payments_first_count,
    u.payments_repeat_count,
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
