-- Расчёт дневной статистики пользователей (МСК).
-- Используется и в кэше (flush dirty / full refresh), и live в горячем окне.
-- Все источники фильтруются по диапазону дат, чтобы избежать full scan по миллионам строк.

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
WITH
-- 1) Границы окна. Если range_start не задан — берём минимум зарегистрированных,
--    чтобы выдать полную историю. p_to NULL → текущий день МСК.
msk_bounds AS (
    SELECT
        (NOW() AT TIME ZONE 'Europe/Moscow')::date AS msk_today,
        (NOW() AT TIME ZONE 'UTC')::date AS utc_today,
        COALESCE(
            (
                SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
                FROM users u
                WHERE u.registered_at IS NOT NULL
                  AND (
                      u.telegram_id IS NOT NULL
                      OR (u.email IS NOT NULL
                          AND BTRIM(u.email) <> ''
                          AND u.email_verified_at IS NOT NULL)
                  )
            ),
            (NOW() AT TIME ZONE 'Europe/Moscow')::date
        ) AS window_start
),
date_window AS (
    SELECT
        COALESCE(p_from, mb.window_start) AS range_start,
        COALESCE(p_to, mb.msk_today) AS range_end,
        mb.utc_today,
        -- На один день раньше нужен для LAG (предыдущий снимок трафика).
        COALESCE(p_from, mb.window_start) - 1 AS traffic_lag_start
    FROM msk_bounds mb
),

-- 2) Квалифицированные / eligible пользователи. Один проход по users.
qualified_users AS (
    SELECT u.id, u.registered_at, u.subscription_until
    FROM users u
    WHERE u.telegram_id IS NOT NULL
       OR (
           u.email IS NOT NULL
           AND BTRIM(u.email) <> ''
           AND u.email_verified_at IS NOT NULL
       )
),
eligible_users AS (
    SELECT id
    FROM qualified_users
    WHERE registered_at IS NOT NULL
      AND subscription_until IS NOT NULL
),

-- 3) Регистрации по дням МСК (фильтр по окну — индекс idx_users_registered_at_msk_date).
reg AS (
    SELECT
        (q.registered_at AT TIME ZONE 'Europe/Moscow')::date AS sd,
        COUNT(*)::bigint AS users_count
    FROM qualified_users q
    INNER JOIN date_window dw
        ON (q.registered_at AT TIME ZONE 'Europe/Moscow')::date
           BETWEEN dw.range_start AND dw.range_end
    WHERE q.registered_at IS NOT NULL
    GROUP BY (q.registered_at AT TIME ZONE 'Europe/Moscow')::date
),

-- 4) Платежи.
--    a) first_payment_meta: один DISTINCT ON по (user_id ORDER BY created_at, id) —
--       использует индекс idx_payments_user_created_at.
--    b) payments_in_window: только платежи в окне (functional index idx_payments_created_at_msk_date).
--    c) payments_by_day: проверяем (user_id, id) против first_payment_meta.
first_payment_meta AS (
    SELECT DISTINCT ON (p.user_id)
        p.user_id,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS first_pay_day,
        p.id AS first_pay_id
    FROM payments p
    INNER JOIN eligible_users eu ON eu.id = p.user_id
    ORDER BY p.user_id, p.created_at ASC, p.id ASC
),
new_payers_by_day AS (
    SELECT
        fp.first_pay_day AS pay_day,
        COUNT(*)::bigint AS users_with_payment_count
    FROM first_payment_meta fp
    INNER JOIN date_window dw ON fp.first_pay_day BETWEEN dw.range_start AND dw.range_end
    GROUP BY fp.first_pay_day
),
payments_in_window AS (
    SELECT
        p.user_id,
        p.id,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS d
    FROM payments p
    INNER JOIN eligible_users eu ON eu.id = p.user_id
    INNER JOIN date_window dw
        ON (p.created_at AT TIME ZONE 'Europe/Moscow')::date
           BETWEEN dw.range_start AND dw.range_end
),
payments_by_day AS (
    SELECT
        piw.d,
        COUNT(*) FILTER (WHERE piw.id = fpm.first_pay_id)::bigint AS payments_first_count,
        COUNT(*) FILTER (WHERE fpm.first_pay_id IS NULL OR piw.id <> fpm.first_pay_id)::bigint
            AS payments_repeat_count
    FROM payments_in_window piw
    LEFT JOIN first_payment_meta fpm ON fpm.user_id = piw.user_id
    GROUP BY piw.d
),
-- Совместимость со старым именованием для traffic_aggs (LEFT JOIN first_payment).
first_payment AS (
    SELECT user_id, first_pay_day FROM first_payment_meta
),

-- 5) Трафик: все снимки до конца окна (как в оригинале — корректный LAG и «первый активный день»).
traffic_snapshots AS (
    SELECT
        t.user_id,
        t.server_id,
        t.traffic_date AS snap_day,
        (t.up_bytes + t.down_bytes)::bigint AS bytes
    FROM user_server_traffic t
    INNER JOIN eligible_users eu ON eu.id = t.user_id
    CROSS JOIN date_window dw
    WHERE t.traffic_date <= dw.range_end
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
-- Один проход по with_prev для всех агрегатов активного трафика.
traffic_aggs AS (
    SELECT
        w.cal_day,
        COUNT(*) FILTER (WHERE w.total > COALESCE(w.prev_total, 0))::bigint
            AS active_users_count,
        COUNT(*) FILTER (
            WHERE w.total > COALESCE(w.prev_total, 0)
              AND fp.user_id IS NOT NULL
        )::bigint AS active_users_with_payment_count,
        COUNT(*) FILTER (
            WHERE w.total > (100::bigint * 1000000 / 8)
        )::bigint AS users_cumulative_traffic_over_100_mbit_count
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    LEFT JOIN first_payment fp
        ON fp.user_id = w.user_id
       AND fp.first_pay_day <= w.cal_day
    GROUP BY w.cal_day
),
user_active_on_day AS (
    SELECT w.cal_day, w.user_id
    FROM with_prev w
    INNER JOIN date_window dw ON w.cal_day BETWEEN dw.range_start AND dw.range_end
    WHERE w.total > COALESCE(w.prev_total, 0)
),
-- Первый активный день за всю историю (не только внутри окна запроса).
traffic_filled_all AS (
    SELECT
        gs.cal_day::date AS cal_day,
        tr.user_id,
        tr.bytes
    FROM traffic_ranges tr
    CROSS JOIN date_window dw
    CROSS JOIN LATERAL generate_series(
        tr.from_day,
        LEAST(
            COALESCE(tr.next_snap_day - 1, dw.range_end),
            dw.range_end
        ),
        interval '1 day'
    ) AS gs (cal_day)
    WHERE tr.from_day <= dw.range_end
),
user_total_all AS (
    SELECT cal_day, user_id, SUM(bytes)::bigint AS total
    FROM traffic_filled_all
    GROUP BY cal_day, user_id
),
with_prev_all AS (
    SELECT
        cal_day,
        user_id,
        total,
        LAG(total) OVER (
            PARTITION BY user_id
            ORDER BY cal_day
        ) AS prev_total
    FROM user_total_all
),
first_user_active_day AS (
    SELECT user_id, MIN(cal_day) AS first_cal
    FROM with_prev_all
    WHERE total > COALESCE(prev_total, 0)
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

-- 6) users_with_traffic_count = пользователи, у которых КОГДА-ЛИБО был трафик > 0,
--    сгруппированные по дню регистрации МСК (в пределах окна).
--    One index-only scan по idx_user_server_traffic_has_traffic + join по reg-day.
users_with_traffic_ever AS (
    SELECT DISTINCT t.user_id
    FROM user_server_traffic t
    WHERE t.up_bytes + t.down_bytes > 0
),
users_with_traffic_by_reg_day AS (
    SELECT
        (q.registered_at AT TIME ZONE 'Europe/Moscow')::date AS reg_day,
        COUNT(*)::bigint AS cnt
    FROM qualified_users q
    INNER JOIN users_with_traffic_ever ut ON ut.user_id = q.id
    INNER JOIN date_window dw
        ON (q.registered_at AT TIME ZONE 'Europe/Moscow')::date
           BETWEEN dw.range_start AND dw.range_end
    WHERE q.registered_at IS NOT NULL
    GROUP BY (q.registered_at AT TIME ZONE 'Europe/Moscow')::date
),

-- 7) Устройства: first_at по eligible-пользователям.
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

-- 8) Активные подписки на конец каждого дня: prefix sum delta start - delta end+1.
--    Подсчитываем baseline до окна и дельты внутри окна — экономнее, чем полная история.
sub_baseline AS (
    SELECT COUNT(*)::bigint AS cnt
    FROM qualified_users q
    INNER JOIN date_window dw ON true
    WHERE q.registered_at IS NOT NULL
      AND q.subscription_until IS NOT NULL
      AND (q.registered_at AT TIME ZONE 'Europe/Moscow')::date < dw.range_start
      AND q.subscription_until::date + 1 > dw.range_start
),
sub_starts_in AS (
    SELECT
        (q.registered_at AT TIME ZONE 'Europe/Moscow')::date AS d,
        COUNT(*)::bigint AS delta
    FROM qualified_users q
    INNER JOIN date_window dw
        ON (q.registered_at AT TIME ZONE 'Europe/Moscow')::date
           BETWEEN dw.range_start AND dw.range_end
    WHERE q.registered_at IS NOT NULL
      AND q.subscription_until IS NOT NULL
    GROUP BY 1
),
sub_ends_in AS (
    SELECT
        (q.subscription_until::date + 1) AS d,
        (-COUNT(*))::bigint AS delta
    FROM qualified_users q
    INNER JOIN date_window dw
        ON (q.subscription_until::date + 1) BETWEEN dw.range_start AND dw.range_end
    WHERE q.registered_at IS NOT NULL
      AND q.subscription_until IS NOT NULL
    GROUP BY 1
),
sub_deltas AS (
    SELECT d, SUM(delta)::bigint AS delta
    FROM (
        SELECT d, delta FROM sub_starts_in
        UNION ALL
        SELECT d, delta FROM sub_ends_in
    ) x
    GROUP BY d
),
dense_calendar AS (
    SELECT generate_series(dw.range_start, dw.range_end, '1 day'::interval)::date AS cal_day
    FROM date_window dw
),
subscription_active_by_day AS (
    SELECT
        dc.cal_day,
        (
            (SELECT COALESCE(cnt, 0) FROM sub_baseline)
            + COALESCE(SUM(sd.delta) OVER (ORDER BY dc.cal_day), 0)
        )::bigint AS users_with_active_subscription_count
    FROM dense_calendar dc
    LEFT JOIN sub_deltas sd ON sd.d = dc.cal_day
),

merged AS (
    SELECT
        dc.cal_day AS stats_date,
        COALESCE(r.users_count, 0)::bigint AS users_count,
        COALESCE(uwt.cnt, 0)::bigint AS users_with_traffic_count,
        CASE
            WHEN dc.cal_day > dw.utc_today THEN NULL
            ELSE COALESCE(ta.active_users_count, 0)::bigint
        END AS active_users_count,
        COALESCE(d.cnt, 0)::bigint AS subscription_devices_users_count,
        CASE
            WHEN dc.cal_day > dw.utc_today THEN NULL
            ELSE COALESCE(ta.users_cumulative_traffic_over_100_mbit_count, 0)::bigint
        END AS users_cumulative_traffic_over_100_mbit_count,
        CASE
            WHEN dc.cal_day > dw.utc_today THEN NULL
            ELSE COALESCE(p.persistent_traffic_users_count, 0)::bigint
        END AS persistent_traffic_users_count,
        COALESCE(np.users_with_payment_count, 0)::bigint AS users_with_payment_count,
        COALESCE(pb.payments_first_count, 0)::bigint AS payments_first_count,
        COALESCE(pb.payments_repeat_count, 0)::bigint AS payments_repeat_count,
        CASE
            WHEN dc.cal_day > dw.utc_today THEN NULL
            ELSE COALESCE(ta.active_users_with_payment_count, 0)::bigint
        END AS active_users_with_payment_count,
        COALESCE(sub.users_with_active_subscription_count, 0)::bigint
            AS users_with_active_subscription_count
    FROM dense_calendar dc
    CROSS JOIN date_window dw
    LEFT JOIN reg r ON r.sd = dc.cal_day
    LEFT JOIN users_with_traffic_by_reg_day uwt ON uwt.reg_day = dc.cal_day
    LEFT JOIN traffic_aggs ta ON ta.cal_day = dc.cal_day
    LEFT JOIN dev d ON d.sd = dc.cal_day
    LEFT JOIN persistent_traffic_users_by_day p ON p.cal_day = dc.cal_day
    LEFT JOIN new_payers_by_day np ON np.pay_day = dc.cal_day
    LEFT JOIN payments_by_day pb ON pb.d = dc.cal_day
    LEFT JOIN subscription_active_by_day sub ON sub.cal_day = dc.cal_day
)
SELECT
    m.stats_date,
    m.users_count,
    m.users_with_traffic_count,
    m.active_users_count,
    m.subscription_devices_users_count,
    m.users_cumulative_traffic_over_100_mbit_count,
    m.persistent_traffic_users_count,
    m.users_with_payment_count,
    m.payments_first_count,
    m.payments_repeat_count,
    m.active_users_with_payment_count,
    m.users_with_active_subscription_count
FROM merged m
ORDER BY m.stats_date NULLS LAST;
$$;
