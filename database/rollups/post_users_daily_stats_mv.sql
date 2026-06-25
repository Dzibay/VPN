-- Кэш дневной пользовательской статистики (Europe/Moscow).
-- Таблица вместо materialized view: REFRESH MV + SQL-функция ломается из-за search_path.
-- Обновление: SELECT fn_refresh_stats_users_daily_msk();

DROP MATERIALIZED VIEW IF EXISTS mv_users_daily_stats;

CREATE TABLE IF NOT EXISTS stats_users_daily_msk (
    stats_date date PRIMARY KEY,
    users_count bigint NOT NULL DEFAULT 0,
    users_with_traffic_count bigint NOT NULL DEFAULT 0,
    active_users_count bigint NOT NULL DEFAULT 0,
    subscription_devices_users_count bigint NOT NULL DEFAULT 0,
    users_cumulative_traffic_over_100_mbit_count bigint NOT NULL DEFAULT 0,
    persistent_traffic_users_count bigint NOT NULL DEFAULT 0,
    users_with_payment_count bigint NOT NULL DEFAULT 0,
    payments_first_count bigint NOT NULL DEFAULT 0,
    payments_repeat_count bigint NOT NULL DEFAULT 0,
    active_users_with_payment_count bigint NOT NULL DEFAULT 0,
    users_with_active_subscription_count bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stats_users_daily_msk_build (
    LIKE stats_users_daily_msk INCLUDING ALL
);

CREATE OR REPLACE FUNCTION fn_stats_users_daily_msk_is_ready ()
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT EXISTS (SELECT 1 FROM stats_users_daily_msk LIMIT 1);
$$;

CREATE OR REPLACE FUNCTION fn_mv_users_daily_stats_is_populated ()
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT fn_stats_users_daily_msk_is_ready();
$$;

CREATE OR REPLACE FUNCTION fn_users_daily_stats_undated_row ()
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
)
SELECT
    NULL::date,
    cnt.users_count,
    cnt.users_with_traffic_count,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint,
    0::bigint
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
WHERE cnt.users_count > 0;
$$;

DROP FUNCTION IF EXISTS fn_refresh_mv_users_daily_stats ();

DROP FUNCTION IF EXISTS fn_refresh_stats_users_daily_msk ();

CREATE OR REPLACE FUNCTION fn_refresh_stats_users_daily_msk ()
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    got_lock boolean;
BEGIN
    got_lock := pg_try_advisory_lock(72491001);
    IF NOT got_lock THEN
        RETURN false;
    END IF;

    TRUNCATE stats_users_daily_msk_build;

    INSERT INTO stats_users_daily_msk_build (
        stats_date,
        users_count,
        users_with_traffic_count,
        active_users_count,
        subscription_devices_users_count,
        users_cumulative_traffic_over_100_mbit_count,
        persistent_traffic_users_count,
        users_with_payment_count,
        payments_first_count,
        payments_repeat_count,
        active_users_with_payment_count,
        users_with_active_subscription_count
    )
    SELECT
        c.stats_date,
        c.users_count,
        c.users_with_traffic_count,
        c.active_users_count,
        c.subscription_devices_users_count,
        c.users_cumulative_traffic_over_100_mbit_count,
        c.persistent_traffic_users_count,
        c.users_with_payment_count,
        c.payments_first_count,
        c.payments_repeat_count,
        c.active_users_with_payment_count,
        c.users_with_active_subscription_count
    FROM fn_users_daily_stats_compute(NULL, NULL) c
    WHERE c.stats_date IS NOT NULL;

    DELETE FROM stats_users_daily_msk;

    INSERT INTO stats_users_daily_msk
    SELECT *
    FROM stats_users_daily_msk_build;

    PERFORM pg_advisory_unlock(72491001);
    RETURN true;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM pg_advisory_unlock(72491001);
        RAISE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_refresh_mv_users_daily_stats ()
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO public
AS $$
BEGIN
    RETURN fn_refresh_stats_users_daily_msk();
END;
$$;

CREATE OR REPLACE FUNCTION rpc_users_daily_stats_baseline (p_before date)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT CASE
    WHEN fn_stats_users_daily_msk_is_ready() THEN (
        SELECT jsonb_build_object(
            'users_count',
            COALESCE(SUM(s.users_count), 0)::bigint,
            'users_with_traffic_count',
            COALESCE(SUM(s.users_with_traffic_count), 0)::bigint,
            'subscription_devices_users_count',
            COALESCE(SUM(s.subscription_devices_users_count), 0)::bigint,
            'users_with_payment_count',
            COALESCE(SUM(s.users_with_payment_count), 0)::bigint
        )
        FROM stats_users_daily_msk s
        WHERE s.stats_date < p_before
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
SET search_path TO public
AS $$
WITH rollup_ready AS (
    SELECT fn_stats_users_daily_msk_is_ready() AS ok
),
msk_bounds AS (
    SELECT
        (NOW() AT TIME ZONE 'Europe/Moscow')::date AS msk_today,
        COALESCE(
            CASE
                WHEN (SELECT ok FROM rollup_ready) THEN (
                    SELECT MIN(s.stats_date)
                    FROM stats_users_daily_msk s
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
from_rollup AS (
    SELECT
        s.stats_date,
        s.users_count,
        s.users_with_traffic_count,
        s.active_users_count,
        s.subscription_devices_users_count,
        s.users_cumulative_traffic_over_100_mbit_count,
        s.persistent_traffic_users_count,
        s.users_with_payment_count,
        s.payments_first_count,
        s.payments_repeat_count,
        s.active_users_with_payment_count,
        s.users_with_active_subscription_count
    FROM stats_users_daily_msk s
    CROSS JOIN date_window dw
    CROSS JOIN rollup_ready r
    WHERE r.ok
      AND s.stats_date BETWEEN dw.range_start AND dw.range_end
),
from_compute AS (
    SELECT c.*
    FROM fn_users_daily_stats_compute(p_from, p_to) c
    CROSS JOIN rollup_ready r
    WHERE NOT r.ok
      AND c.stats_date IS NOT NULL
),
dated_rows AS (
    SELECT * FROM from_rollup
    UNION ALL
    SELECT * FROM from_compute
),
undated AS (
    SELECT u.*
    FROM fn_users_daily_stats_undated_row() u
    CROSS JOIN rollup_ready r
    WHERE r.ok
    UNION ALL
    SELECT c.*
    FROM fn_users_daily_stats_compute(p_from, p_to) c
    CROSS JOIN rollup_ready r
    WHERE NOT r.ok
      AND c.stats_date IS NULL
)
SELECT *
FROM (
    SELECT * FROM dated_rows
    UNION ALL
    SELECT * FROM undated
) x
ORDER BY x.stats_date NULLS LAST;
$$;
