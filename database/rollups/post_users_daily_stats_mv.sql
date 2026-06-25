-- Кэш дневной пользовательской статистики (Europe/Moscow).
-- Умный режим: «холодная» история в stats_users_daily_msk (триггеры + flush),
-- последние fn_stats_users_daily_hot_days() суток — live-compute на чтении.
-- Полный пересчёт: SELECT fn_refresh_stats_users_daily_msk();

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

-- Строка stats_date = NULL: пользователи без registered_at.
-- Использует партиционный индекс idx_user_server_traffic_has_traffic.
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
SELECT
    NULL::date,
    cnt.users_count,
    cnt.users_with_traffic_count,
    0::bigint, 0::bigint, 0::bigint, 0::bigint,
    0::bigint, 0::bigint, 0::bigint, 0::bigint, 0::bigint
FROM (
    SELECT
        COUNT(*)::bigint AS users_count,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1 FROM user_server_traffic t
                WHERE t.user_id = u.id AND t.up_bytes + t.down_bytes > 0
            )
        )::bigint AS users_with_traffic_count
    FROM users u
    WHERE u.registered_at IS NULL
      AND (
          u.telegram_id IS NOT NULL
          OR (u.email IS NOT NULL
              AND BTRIM(u.email) <> ''
              AND u.email_verified_at IS NOT NULL)
      )
) cnt
WHERE cnt.users_count > 0;
$$;

DROP FUNCTION IF EXISTS fn_refresh_mv_users_daily_stats ();

DROP FUNCTION IF EXISTS fn_refresh_stats_users_daily_msk ();

CREATE OR REPLACE FUNCTION fn_stats_users_daily_flush_dirty ()
RETURNS integer
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    got_lock boolean;
    d_min date;
    d_max date;
    cold_to date;
    flush_to date;
    n integer;
BEGIN
    got_lock := pg_try_advisory_lock(72491002);
    IF NOT got_lock THEN
        RETURN 0;
    END IF;

    cold_to := fn_stats_users_daily_hot_start() - 1;
    IF cold_to < '1970-01-01'::date THEN
        PERFORM pg_advisory_unlock(72491002);
        RETURN 0;
    END IF;

    SELECT MIN(stats_date), MAX(stats_date)
    INTO d_min, d_max
    FROM stats_users_daily_dirty
    WHERE stats_date <= cold_to;

    IF d_min IS NULL THEN
        PERFORM pg_advisory_unlock(72491002);
        RETURN 0;
    END IF;

    flush_to := LEAST(d_max, cold_to);

    INSERT INTO stats_users_daily_msk (
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
    FROM fn_users_daily_stats_compute(d_min, flush_to) c
    WHERE c.stats_date IS NOT NULL
    ON CONFLICT (stats_date) DO UPDATE
    SET
        users_count = EXCLUDED.users_count,
        users_with_traffic_count = EXCLUDED.users_with_traffic_count,
        active_users_count = EXCLUDED.active_users_count,
        subscription_devices_users_count = EXCLUDED.subscription_devices_users_count,
        users_cumulative_traffic_over_100_mbit_count = EXCLUDED.users_cumulative_traffic_over_100_mbit_count,
        persistent_traffic_users_count = EXCLUDED.persistent_traffic_users_count,
        users_with_payment_count = EXCLUDED.users_with_payment_count,
        payments_first_count = EXCLUDED.payments_first_count,
        payments_repeat_count = EXCLUDED.payments_repeat_count,
        active_users_with_payment_count = EXCLUDED.active_users_with_payment_count,
        users_with_active_subscription_count = EXCLUDED.users_with_active_subscription_count;

    GET DIAGNOSTICS n = ROW_COUNT;

    DELETE FROM stats_users_daily_dirty
    WHERE stats_date BETWEEN d_min AND flush_to;

    PERFORM pg_advisory_unlock(72491002);
    RETURN n;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM pg_advisory_unlock(72491002);
        RAISE;
END;
$$;

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

    DELETE FROM stats_users_daily_dirty
    WHERE stats_date < fn_stats_users_daily_hot_start();

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

-- Baseline = накопительные счётчики до p_before (для частичных периодов).
-- Использует rpc_users_daily_stats(NULL, p_before-1) — один compute,
-- кэш + горячее окно обрабатываются единообразно.
CREATE OR REPLACE FUNCTION rpc_users_daily_stats_baseline (p_before date)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT jsonb_build_object(
    'users_count', COALESCE(SUM(s.users_count), 0)::bigint,
    'users_with_traffic_count', COALESCE(SUM(s.users_with_traffic_count), 0)::bigint,
    'subscription_devices_users_count',
        COALESCE(SUM(s.subscription_devices_users_count), 0)::bigint,
    'users_with_payment_count', COALESCE(SUM(s.users_with_payment_count), 0)::bigint
)
FROM rpc_users_daily_stats(NULL, p_before - 1) s
WHERE s.stats_date IS NOT NULL AND s.stats_date < p_before;
$$;

-- Главная функция чтения статистики.
-- Стратегия:
--   * холодная часть периода (stats_date < hot_start) — из кэша stats_users_daily_msk,
--     если он построен; иначе один compute по холодной части.
--   * горячая часть (>= hot_start) — один compute по горячей части.
-- НИ В КОЕМ СЛУЧАЕ не вызываем fn_users_daily_stats_compute дважды.
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
LANGUAGE plpgsql
STABLE
SET search_path TO public
AS $$
DECLARE
    v_msk_today date := (NOW() AT TIME ZONE 'Europe/Moscow')::date;
    v_hot_start date := fn_stats_users_daily_hot_start();
    v_ready boolean := fn_stats_users_daily_msk_is_ready();
    v_window_start date;
    v_range_start date;
    v_range_end date;
    v_cold_end date;
    v_hot_begin date;
BEGIN
    -- window_start: минимальный известный день (из кэша или users)
    IF v_ready THEN
        SELECT MIN(s.stats_date) INTO v_window_start FROM stats_users_daily_msk s;
    END IF;
    IF v_window_start IS NULL THEN
        SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
        INTO v_window_start
        FROM users u
        WHERE u.registered_at IS NOT NULL;
    END IF;
    v_window_start := COALESCE(v_window_start, v_msk_today);

    v_range_start := COALESCE(p_from, v_window_start);
    v_range_end := COALESCE(p_to, v_msk_today);

    v_cold_end := LEAST(v_range_end, v_hot_start - 1);
    v_hot_begin := GREATEST(v_range_start, v_hot_start);

    -- 1) холодная часть периода
    IF v_range_start <= v_cold_end THEN
        IF v_ready THEN
            RETURN QUERY
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
            WHERE s.stats_date BETWEEN v_range_start AND v_cold_end;
        ELSE
            RETURN QUERY
            SELECT c.*
            FROM fn_users_daily_stats_compute(v_range_start, v_cold_end) c
            WHERE c.stats_date IS NOT NULL;
        END IF;
    END IF;

    -- 2) горячая часть всегда из compute (live, без кэша)
    IF v_range_end >= v_hot_start THEN
        RETURN QUERY
        SELECT c.*
        FROM fn_users_daily_stats_compute(v_hot_begin, v_range_end) c
        WHERE c.stats_date IS NOT NULL;
    END IF;

    -- 3) строка undated
    RETURN QUERY
    SELECT u.*
    FROM fn_users_daily_stats_undated_row() u;
END;
$$;
