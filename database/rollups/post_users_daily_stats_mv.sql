-- Materialized view дневной пользовательской статистики (Europe/Moscow).
-- Обновляется после сбора трафика Xray: SELECT fn_refresh_mv_users_daily_stats();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'public'
          AND matviewname = 'mv_users_daily_stats'
    ) THEN
        CREATE MATERIALIZED VIEW mv_users_daily_stats AS
        SELECT *
        FROM fn_users_daily_stats_compute(NULL, NULL)
        WHERE stats_date IS NOT NULL
        WITH NO DATA;
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_users_daily_stats_date
    ON mv_users_daily_stats (stats_date);

CREATE OR REPLACE FUNCTION fn_mv_users_daily_stats_is_populated ()
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
SELECT COALESCE(
    (
        SELECT m.ispopulated
        FROM pg_catalog.pg_matviews m
        WHERE m.schemaname = 'public'
          AND m.matviewname = 'mv_users_daily_stats'
    ),
    false
);
$$;

CREATE OR REPLACE FUNCTION fn_refresh_mv_users_daily_stats ()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'public'
          AND matviewname = 'mv_users_daily_stats'
    ) THEN
        RETURN;
    END IF;

    IF NOT fn_mv_users_daily_stats_is_populated() THEN
        REFRESH MATERIALIZED VIEW mv_users_daily_stats;
        RETURN;
    END IF;

    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_users_daily_stats;
EXCEPTION
    WHEN object_not_in_prerequisite_state THEN
        REFRESH MATERIALIZED VIEW mv_users_daily_stats;
END;
$$;

CREATE OR REPLACE FUNCTION rpc_users_daily_stats_baseline (p_before date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
SELECT CASE
    WHEN fn_mv_users_daily_stats_is_populated() THEN (
        SELECT jsonb_build_object(
            'users_count',
            COALESCE(SUM(m.users_count), 0)::bigint,
            'users_with_traffic_count',
            COALESCE(SUM(m.users_with_traffic_count), 0)::bigint,
            'subscription_devices_users_count',
            COALESCE(SUM(m.subscription_devices_users_count), 0)::bigint,
            'users_with_payment_count',
            COALESCE(SUM(m.users_with_payment_count), 0)::bigint
        )
        FROM mv_users_daily_stats m
        WHERE m.stats_date < p_before
    )
    ELSE (
        SELECT jsonb_build_object(
            'users_count',
            COALESCE(SUM(c.users_count), 0)::bigint,
            'users_with_traffic_count',
            COALESCE(SUM(c.users_with_traffic_count), 0)::bigint,
            'subscription_devices_users_count',
            COALESCE(SUM(c.subscription_devices_users_count), 0)::bigint,
            'users_with_payment_count',
            COALESCE(SUM(c.users_with_payment_count), 0)::bigint
        )
        FROM fn_users_daily_stats_compute(NULL, p_before - 1) c
        WHERE c.stats_date IS NOT NULL
    )
END;
$$;

CREATE OR REPLACE FUNCTION rpc_users_daily_stats (
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
AS $$
WITH mv_ready AS (
    SELECT fn_mv_users_daily_stats_is_populated() AS ok
),
msk_bounds AS (
    SELECT
        (NOW() AT TIME ZONE 'Europe/Moscow')::date AS msk_today,
        COALESCE(
            CASE
                WHEN (SELECT ok FROM mv_ready) THEN (
                    SELECT MIN(m.stats_date)
                    FROM mv_users_daily_stats m
                )
            END,
            (
                SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
                FROM users u
                WHERE u.registered_at IS NOT NULL
            ),
            (NOW() AT TIME ZONE 'Europe/Moscow')::date
        ) AS window_start
),
date_window AS (
    SELECT
        COALESCE(p_from, mb.window_start) AS range_start,
        COALESCE(p_to, mb.msk_today) AS range_end
    FROM msk_bounds mb
),
from_mv AS (
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
    FROM mv_users_daily_stats m
    CROSS JOIN date_window dw
    CROSS JOIN mv_ready r
    WHERE r.ok
      AND m.stats_date BETWEEN dw.range_start AND dw.range_end
),
from_compute AS (
    SELECT c.*
    FROM fn_users_daily_stats_compute(p_from, p_to) c
    CROSS JOIN mv_ready r
    WHERE NOT r.ok
      AND c.stats_date IS NOT NULL
),
dated_rows AS (
    SELECT * FROM from_mv
    UNION ALL
    SELECT * FROM from_compute
),
undated AS (
    SELECT u.*
    FROM fn_users_daily_stats_compute(p_from, p_to) u
    CROSS JOIN mv_ready r
    WHERE NOT r.ok
      AND u.stats_date IS NULL
    UNION ALL
    SELECT u.*
    FROM fn_users_daily_stats_compute(p_from, p_to) u
    CROSS JOIN mv_ready r
    WHERE r.ok
      AND u.stats_date IS NULL
)
SELECT *
FROM (
    SELECT * FROM dated_rows
    UNION ALL
    SELECT * FROM undated
) x
ORDER BY x.stats_date NULLS LAST;
$$;
