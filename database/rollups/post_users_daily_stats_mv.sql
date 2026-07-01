-- Кэш дневной пользовательской статистики (Europe/Moscow), multi-tenant.
-- Ключ (project_id, stats_date): каждый проект имеет свой кэш.
-- Полный пересчёт для одного проекта: SELECT fn_refresh_stats_users_daily_msk(1);
-- Полный пересчёт для всех проектов: SELECT fn_refresh_stats_users_daily_msk_all();

DROP MATERIALIZED VIEW IF EXISTS mv_users_daily_stats;

-- Убираем старые (single-tenant) сигнатуры, чтобы CREATE OR REPLACE ниже не создавал
-- вторую перегрузку — иначе SQL-вызовы будут падать на ambiguity.
DROP FUNCTION IF EXISTS fn_stats_users_daily_msk_is_ready();
DROP FUNCTION IF EXISTS fn_users_daily_stats_undated_row();
DROP FUNCTION IF EXISTS fn_stats_users_daily_msk_build_fill(date, date);
DROP FUNCTION IF EXISTS fn_refresh_stats_users_daily_msk();
DROP FUNCTION IF EXISTS rpc_users_daily_stats(date, date);
DROP FUNCTION IF EXISTS rpc_users_daily_stats_baseline(date);

CREATE TABLE IF NOT EXISTS stats_users_daily_msk (
    stats_date date NOT NULL,
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

-- Multi-tenant миграция: добавляем project_id в PK. Если старый PK был по (stats_date),
-- backfill в migrate.sql перенастроит его; здесь только IF NOT EXISTS-опции.
DO $mig$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_users_daily_msk' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_users_daily_msk
            ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1
                REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE stats_users_daily_msk ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_users_daily_msk DROP CONSTRAINT IF EXISTS stats_users_daily_msk_pkey;
        ALTER TABLE stats_users_daily_msk
            ADD CONSTRAINT stats_users_daily_msk_pkey
                PRIMARY KEY (project_id, stats_date);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_users_daily_msk_build' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_users_daily_msk_build
            ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1;
        ALTER TABLE stats_users_daily_msk_build ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_users_daily_msk_build DROP CONSTRAINT IF EXISTS stats_users_daily_msk_build_pkey;
        ALTER TABLE stats_users_daily_msk_build
            ADD CONSTRAINT stats_users_daily_msk_build_pkey
                PRIMARY KEY (project_id, stats_date);
    END IF;
END $mig$;

CREATE INDEX IF NOT EXISTS idx_stats_users_daily_msk_date
    ON stats_users_daily_msk (stats_date);

CREATE OR REPLACE FUNCTION fn_stats_users_daily_msk_is_ready (p_project_id bigint DEFAULT NULL)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT EXISTS (
    SELECT 1
    FROM stats_users_daily_msk s
    WHERE p_project_id IS NULL OR s.project_id = p_project_id
    LIMIT 1
);
$$;

CREATE OR REPLACE FUNCTION fn_mv_users_daily_stats_is_populated ()
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT fn_stats_users_daily_msk_is_ready(NULL);
$$;

-- Строка stats_date = NULL: пользователи без registered_at (для конкретного проекта).
CREATE OR REPLACE FUNCTION fn_users_daily_stats_undated_row (p_project_id bigint DEFAULT NULL)
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
      AND (p_project_id IS NULL OR u.project_id = p_project_id)
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

-- Заполняет staging-таблицу для одного проекта (тяжёлый compute).
CREATE OR REPLACE FUNCTION fn_stats_users_daily_msk_build_fill (
    p_project_id bigint,
    p_from date,
    p_to date
)
RETURNS void
LANGUAGE plpgsql
SET search_path TO public
AS $$
BEGIN
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'fn_stats_users_daily_msk_build_fill: p_project_id обязателен';
    END IF;

    DELETE FROM stats_users_daily_msk_build
    WHERE project_id = p_project_id;

    INSERT INTO stats_users_daily_msk_build (
        project_id,
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
        p_project_id,
        c.stats_date,
        c.users_count,
        c.users_with_traffic_count,
        COALESCE(c.active_users_count, 0),
        c.subscription_devices_users_count,
        COALESCE(c.users_cumulative_traffic_over_100_mbit_count, 0),
        COALESCE(c.persistent_traffic_users_count, 0),
        c.users_with_payment_count,
        c.payments_first_count,
        c.payments_repeat_count,
        COALESCE(c.active_users_with_payment_count, 0),
        c.users_with_active_subscription_count
    FROM fn_users_daily_stats_compute(p_from, p_to, p_project_id) c
    WHERE c.stats_date IS NOT NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_flush_max_days ()
RETURNS integer
LANGUAGE sql
IMMUTABLE
SET search_path TO public
AS $$
SELECT 31;
$$;

-- Инкрементальный flush для одного проекта.
CREATE OR REPLACE FUNCTION fn_stats_users_daily_flush_dirty_project (p_project_id bigint)
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
    cold_to := fn_stats_users_daily_hot_start() - 1;
    IF cold_to < '1970-01-01'::date THEN
        RETURN 0;
    END IF;

    SELECT MIN(stats_date), MAX(stats_date)
    INTO d_min, d_max
    FROM stats_users_daily_dirty
    WHERE project_id = p_project_id AND stats_date <= cold_to;

    IF d_min IS NULL THEN
        RETURN 0;
    END IF;

    flush_to := LEAST(
        d_max,
        cold_to,
        d_min + fn_stats_users_daily_flush_max_days() - 1
    );

    PERFORM fn_stats_users_daily_msk_build_fill(p_project_id, d_min, flush_to);

    got_lock := pg_try_advisory_lock(72491002, p_project_id::integer);
    IF NOT got_lock THEN
        RETURN 0;
    END IF;

    INSERT INTO stats_users_daily_msk (
        project_id,
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
        project_id, stats_date, users_count, users_with_traffic_count,
        active_users_count, subscription_devices_users_count,
        users_cumulative_traffic_over_100_mbit_count, persistent_traffic_users_count,
        users_with_payment_count, payments_first_count, payments_repeat_count,
        active_users_with_payment_count, users_with_active_subscription_count
    FROM stats_users_daily_msk_build
    WHERE project_id = p_project_id
    ON CONFLICT (project_id, stats_date) DO UPDATE
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
    WHERE project_id = p_project_id AND stats_date BETWEEN d_min AND flush_to;

    PERFORM pg_advisory_unlock(72491002, p_project_id::integer);
    RETURN n;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM pg_advisory_unlock(72491002, p_project_id::integer);
        RAISE;
END;
$$;

-- Совместимость: flush по всем проектам (используется в scheduler).
CREATE OR REPLACE FUNCTION fn_stats_users_daily_flush_dirty ()
RETURNS integer
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    total integer := 0;
    pid bigint;
BEGIN
    FOR pid IN
        SELECT DISTINCT project_id FROM stats_users_daily_dirty
    LOOP
        total := total + COALESCE(fn_stats_users_daily_flush_dirty_project(pid), 0);
    END LOOP;
    RETURN total;
END;
$$;

CREATE OR REPLACE FUNCTION fn_refresh_stats_users_daily_msk (p_project_id bigint)
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    got_lock boolean;
BEGIN
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'fn_refresh_stats_users_daily_msk: p_project_id обязателен (используйте fn_refresh_stats_users_daily_msk_all() для всех)';
    END IF;

    PERFORM fn_stats_users_daily_msk_build_fill(p_project_id, NULL, NULL);

    got_lock := pg_try_advisory_lock(72491001, p_project_id::integer);
    IF NOT got_lock THEN
        RETURN false;
    END IF;

    DELETE FROM stats_users_daily_msk WHERE project_id = p_project_id;

    INSERT INTO stats_users_daily_msk
    SELECT * FROM stats_users_daily_msk_build WHERE project_id = p_project_id;

    DELETE FROM stats_users_daily_dirty
    WHERE project_id = p_project_id AND stats_date < fn_stats_users_daily_hot_start();

    PERFORM pg_advisory_unlock(72491001, p_project_id::integer);
    RETURN true;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM pg_advisory_unlock(72491001, p_project_id::integer);
        RAISE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_refresh_stats_users_daily_msk_all ()
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    pid bigint;
    ok boolean := true;
BEGIN
    FOR pid IN SELECT id FROM projects WHERE is_active = TRUE LOOP
        IF NOT fn_refresh_stats_users_daily_msk(pid) THEN
            ok := false;
        END IF;
    END LOOP;
    RETURN ok;
END;
$$;

CREATE OR REPLACE FUNCTION fn_refresh_mv_users_daily_stats ()
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO public
AS $$
BEGIN
    RETURN fn_refresh_stats_users_daily_msk_all();
END;
$$;

-- Главная функция чтения статистики. p_project_id=NULL — агрегат по всем проектам.
CREATE OR REPLACE FUNCTION rpc_users_daily_stats (
    p_from date DEFAULT NULL,
    p_to date DEFAULT NULL,
    p_project_id bigint DEFAULT NULL
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
    v_ready boolean := fn_stats_users_daily_msk_is_ready(p_project_id);
    v_window_start date;
    v_range_start date;
    v_range_end date;
    v_cold_end date;
    v_hot_begin date;
BEGIN
    IF v_ready THEN
        SELECT MIN(s.stats_date) INTO v_window_start
        FROM stats_users_daily_msk s
        WHERE p_project_id IS NULL OR s.project_id = p_project_id;
    END IF;
    IF v_window_start IS NULL THEN
        SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
        INTO v_window_start
        FROM users u
        WHERE u.registered_at IS NOT NULL
          AND (p_project_id IS NULL OR u.project_id = p_project_id);
    END IF;
    v_window_start := COALESCE(v_window_start, v_msk_today);

    v_range_start := COALESCE(p_from, v_window_start);
    v_range_end := COALESCE(p_to, v_msk_today);

    v_cold_end := LEAST(v_range_end, v_hot_start - 1);
    v_hot_begin := GREATEST(v_range_start, v_hot_start);

    IF v_range_start <= v_cold_end THEN
        IF v_ready THEN
            IF EXISTS (
                SELECT 1
                FROM generate_series(v_range_start, v_cold_end, interval '1 day') gs (d)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM stats_users_daily_msk s
                    WHERE s.stats_date = gs.d::date
                      AND (p_project_id IS NULL OR s.project_id = p_project_id)
                )
            ) OR EXISTS (
                SELECT 1
                FROM stats_users_daily_dirty d
                WHERE d.stats_date BETWEEN v_range_start AND v_cold_end
                  AND (p_project_id IS NULL OR d.project_id = p_project_id)
            ) THEN
                RETURN QUERY
                SELECT c.*
                FROM fn_users_daily_stats_compute(v_range_start, v_cold_end, p_project_id) c
                WHERE c.stats_date IS NOT NULL;
            ELSE
                RETURN QUERY
                SELECT
                    s.stats_date,
                    SUM(s.users_count)::bigint,
                    SUM(s.users_with_traffic_count)::bigint,
                    SUM(s.active_users_count)::bigint,
                    SUM(s.subscription_devices_users_count)::bigint,
                    SUM(s.users_cumulative_traffic_over_100_mbit_count)::bigint,
                    SUM(s.persistent_traffic_users_count)::bigint,
                    SUM(s.users_with_payment_count)::bigint,
                    SUM(s.payments_first_count)::bigint,
                    SUM(s.payments_repeat_count)::bigint,
                    SUM(s.active_users_with_payment_count)::bigint,
                    SUM(s.users_with_active_subscription_count)::bigint
                FROM stats_users_daily_msk s
                WHERE s.stats_date BETWEEN v_range_start AND v_cold_end
                  AND (p_project_id IS NULL OR s.project_id = p_project_id)
                GROUP BY s.stats_date
                ORDER BY s.stats_date;
            END IF;
        ELSE
            RETURN QUERY
            SELECT c.*
            FROM fn_users_daily_stats_compute(v_range_start, v_cold_end, p_project_id) c
            WHERE c.stats_date IS NOT NULL;
        END IF;
    END IF;

    IF v_range_end >= v_hot_start THEN
        RETURN QUERY
        SELECT c.*
        FROM fn_users_daily_stats_compute(v_hot_begin, v_range_end, p_project_id) c
        WHERE c.stats_date IS NOT NULL;
    END IF;

    RETURN QUERY
    SELECT u.*
    FROM fn_users_daily_stats_undated_row(p_project_id) u;
END;
$$;

CREATE OR REPLACE FUNCTION rpc_users_daily_stats_baseline (
    p_before date,
    p_project_id bigint DEFAULT NULL
)
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
FROM rpc_users_daily_stats(NULL::date, p_before - 1, p_project_id) s
WHERE s.stats_date IS NOT NULL AND s.stats_date < p_before;
$$;
