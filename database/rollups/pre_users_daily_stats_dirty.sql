-- Multi-tenant очередь «грязных» дней + триггеры на источники.
-- PK: (project_id, stats_date). Триггеры пишут project_id из NEW/OLD-строк.

-- Убираем старые (single-tenant) сигнатуры, чтобы CREATE OR REPLACE ниже не создавал
-- вторую перегрузку — иначе SQL-вызовы будут падать на ambiguity.
DROP FUNCTION IF EXISTS fn_stats_users_daily_mark_dirty(date, date);
DROP FUNCTION IF EXISTS fn_stats_users_daily_mark_recent_cold_dirty(integer);
DROP FUNCTION IF EXISTS fn_stats_users_daily_mark_cache_gaps_dirty();

CREATE TABLE IF NOT EXISTS stats_users_daily_dirty (
    stats_date date NOT NULL,
    dirty_at timestamptz NOT NULL DEFAULT now()
);

DO $mig$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_users_daily_dirty' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_users_daily_dirty
            ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1
                REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE stats_users_daily_dirty ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_users_daily_dirty DROP CONSTRAINT IF EXISTS stats_users_daily_dirty_pkey;
        ALTER TABLE stats_users_daily_dirty
            ADD CONSTRAINT stats_users_daily_dirty_pkey
                PRIMARY KEY (project_id, stats_date);
    END IF;
END $mig$;

CREATE INDEX IF NOT EXISTS idx_stats_users_daily_dirty_at
    ON stats_users_daily_dirty (dirty_at);

CREATE OR REPLACE FUNCTION fn_stats_users_daily_hot_days ()
RETURNS integer
LANGUAGE sql
IMMUTABLE
SET search_path TO public
AS $$
SELECT 14;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_hot_start ()
RETURNS date
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT (
    (NOW() AT TIME ZONE 'Europe/Moscow')::date
    - (fn_stats_users_daily_hot_days() - 1)
)::date;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_mark_dirty (
    p_project_id bigint,
    p_from date,
    p_to date
)
RETURNS void
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    d_from date;
    d_to date;
    cold_to date;
BEGIN
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'fn_stats_users_daily_mark_dirty: p_project_id обязателен';
    END IF;
    IF p_from IS NULL AND p_to IS NULL THEN
        RETURN;
    END IF;

    cold_to := fn_stats_users_daily_hot_start() - 1;
    IF cold_to < '1970-01-01'::date THEN
        RETURN;
    END IF;

    d_from := COALESCE(p_from, cold_to);
    d_to := COALESCE(p_to, cold_to);
    d_from := LEAST(d_from, d_to);
    d_to := GREATEST(d_from, d_to);
    d_from := GREATEST(d_from, '1970-01-01'::date);
    d_to := LEAST(d_to, cold_to);

    IF d_from > d_to THEN
        RETURN;
    END IF;

    INSERT INTO stats_users_daily_dirty (project_id, stats_date)
    SELECT p_project_id, gs::date
    FROM generate_series(d_from, d_to, interval '1 day') AS gs
    ON CONFLICT (project_id, stats_date) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_mark_recent_cold_dirty (
    p_project_id bigint,
    p_days integer DEFAULT 90
)
RETURNS void
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    pid bigint;
BEGIN
    IF p_project_id IS NOT NULL THEN
        PERFORM fn_stats_users_daily_mark_dirty(
            p_project_id,
            fn_stats_users_daily_hot_start() - GREATEST(p_days, 1),
            fn_stats_users_daily_hot_start() - 1
        );
        RETURN;
    END IF;
    FOR pid IN SELECT id FROM projects WHERE is_active = TRUE LOOP
        PERFORM fn_stats_users_daily_mark_dirty(
            pid,
            fn_stats_users_daily_hot_start() - GREATEST(p_days, 1),
            fn_stats_users_daily_hot_start() - 1
        );
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_dirty_count ()
RETURNS bigint
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT COUNT(*)::bigint FROM stats_users_daily_dirty;
$$;

-- Пометить холодные дни, отсутствующие в кэше (догон после частичного заполнения),
-- для одного проекта.
CREATE OR REPLACE FUNCTION fn_stats_users_daily_mark_cache_gaps_dirty (
    p_project_id bigint
)
RETURNS integer
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    cold_to date := fn_stats_users_daily_hot_start() - 1;
    d_from date;
    n integer;
BEGIN
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'fn_stats_users_daily_mark_cache_gaps_dirty: p_project_id обязателен';
    END IF;
    IF cold_to < '1970-01-01'::date THEN
        RETURN 0;
    END IF;

    SELECT MIN((u.registered_at AT TIME ZONE 'Europe/Moscow')::date)
    INTO d_from
    FROM users u
    WHERE u.registered_at IS NOT NULL
      AND u.project_id = p_project_id
      AND (
          u.telegram_id IS NOT NULL
          OR (
              u.email IS NOT NULL
              AND BTRIM(u.email) <> ''
              AND u.email_verified_at IS NOT NULL
          )
      );

    d_from := COALESCE(d_from, cold_to);
    IF d_from > cold_to THEN
        RETURN 0;
    END IF;

    INSERT INTO stats_users_daily_dirty (project_id, stats_date)
    SELECT p_project_id, gs::date
    FROM generate_series(d_from, cold_to, interval '1 day') AS gs
    WHERE NOT EXISTS (
        SELECT 1
        FROM stats_users_daily_msk s
        WHERE s.project_id = p_project_id AND s.stats_date = gs::date
    )
    ON CONFLICT (project_id, stats_date) DO NOTHING;

    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;

-- --- триггеры ---

CREATE OR REPLACE FUNCTION trg_users_daily_stats_dirty ()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    cold_to date := fn_stats_users_daily_hot_start() - 1;
    d_from date := NULL;
    d_to date := NULL;
    d date;
    candidates date[];
    pid bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        pid := OLD.project_id;
        candidates := ARRAY[
            CASE WHEN OLD.registered_at IS NOT NULL
                 THEN (OLD.registered_at AT TIME ZONE 'Europe/Moscow')::date END,
            CASE WHEN OLD.subscription_until IS NOT NULL
                 THEN OLD.subscription_until::date + 1 END
        ];
    ELSE
        pid := NEW.project_id;
        IF TG_OP = 'UPDATE' AND NOT (
            OLD.registered_at IS DISTINCT FROM NEW.registered_at
            OR OLD.subscription_until IS DISTINCT FROM NEW.subscription_until
            OR OLD.email IS DISTINCT FROM NEW.email
            OR OLD.email_verified_at IS DISTINCT FROM NEW.email_verified_at
            OR OLD.telegram_id IS DISTINCT FROM NEW.telegram_id
        ) THEN
            RETURN NEW;
        END IF;

        candidates := ARRAY[
            CASE WHEN NEW.registered_at IS NOT NULL
                 THEN (NEW.registered_at AT TIME ZONE 'Europe/Moscow')::date END,
            CASE WHEN NEW.subscription_until IS NOT NULL
                 THEN NEW.subscription_until::date + 1 END,
            CASE WHEN TG_OP = 'UPDATE' AND OLD.registered_at IS NOT NULL
                 THEN (OLD.registered_at AT TIME ZONE 'Europe/Moscow')::date END,
            CASE WHEN TG_OP = 'UPDATE' AND OLD.subscription_until IS NOT NULL
                 THEN OLD.subscription_until::date + 1 END
        ];
    END IF;

    FOREACH d IN ARRAY candidates LOOP
        IF d IS NULL OR d > cold_to THEN
            CONTINUE;
        END IF;
        IF d_from IS NULL OR d < d_from THEN d_from := d; END IF;
        IF d_to IS NULL OR d > d_to THEN d_to := d; END IF;
    END LOOP;

    IF d_from IS NOT NULL AND pid IS NOT NULL THEN
        PERFORM fn_stats_users_daily_mark_dirty(pid, d_from, d_to);
    END IF;

    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_daily_stats_dirty ON users;

CREATE TRIGGER trg_users_daily_stats_dirty
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW
EXECUTE FUNCTION trg_users_daily_stats_dirty ();

CREATE OR REPLACE FUNCTION trg_payments_users_daily_stats_dirty ()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    cold_to date := fn_stats_users_daily_hot_start() - 1;
    d_old date;
    d_new date;
    d_from date;
    d_to date;
    pid bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        pid := OLD.project_id;
        d_old := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
        IF pid IS NOT NULL AND d_old <= cold_to THEN
            PERFORM fn_stats_users_daily_mark_dirty(pid, d_old, d_old);
        END IF;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        pid := NEW.project_id;
        d_old := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
        d_new := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
        d_from := LEAST(d_old, d_new);
        d_to := LEAST(GREATEST(d_old, d_new), cold_to);
        IF pid IS NOT NULL AND d_from <= cold_to THEN
            PERFORM fn_stats_users_daily_mark_dirty(pid, d_from, d_to);
        END IF;
        RETURN NEW;
    END IF;

    pid := NEW.project_id;
    d_new := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
    IF pid IS NOT NULL AND d_new <= cold_to THEN
        PERFORM fn_stats_users_daily_mark_dirty(pid, d_new, d_new);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_payments_users_daily_stats_dirty ON payments;

CREATE TRIGGER trg_payments_users_daily_stats_dirty
AFTER INSERT OR UPDATE OR DELETE ON payments
FOR EACH ROW
EXECUTE FUNCTION trg_payments_users_daily_stats_dirty ();

CREATE OR REPLACE FUNCTION trg_subscription_devices_daily_stats_dirty ()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    cold_to date := fn_stats_users_daily_hot_start() - 1;
    d_day date;
    pid bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        pid := OLD.project_id;
        d_day := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
    ELSE
        pid := NEW.project_id;
        d_day := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
    END IF;

    IF pid IS NOT NULL AND d_day <= cold_to THEN
        PERFORM fn_stats_users_daily_mark_dirty(pid, d_day, d_day);
    END IF;

    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_subscription_devices_daily_stats_dirty ON subscription_devices;

CREATE TRIGGER trg_subscription_devices_daily_stats_dirty
AFTER INSERT OR DELETE ON subscription_devices
FOR EACH ROW
EXECUTE FUNCTION trg_subscription_devices_daily_stats_dirty ();

-- Statement-level trigger по трафику: помечаем dirty ПО КАЖДОМУ project_id, встречающемуся
-- в OLD/NEW-строках. Один проход через GROUP BY project_id.
CREATE OR REPLACE FUNCTION trg_user_server_traffic_stats_dirty_stmt ()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    cold_to date := fn_stats_users_daily_hot_start() - 1;
    rec RECORD;
BEGIN
    IF TG_OP = 'DELETE' THEN
        FOR rec IN
            SELECT project_id, MIN(traffic_date) AS d_min, MAX(traffic_date) AS d_max
            FROM old_traffic
            GROUP BY project_id
        LOOP
            IF rec.d_min IS NOT NULL AND rec.d_min <= cold_to AND rec.project_id IS NOT NULL THEN
                PERFORM fn_stats_users_daily_mark_dirty(
                    rec.project_id, rec.d_min - 1, LEAST(rec.d_max, cold_to)
                );
            END IF;
        END LOOP;
    ELSE
        FOR rec IN
            SELECT project_id, MIN(traffic_date) AS d_min, MAX(traffic_date) AS d_max
            FROM new_traffic
            GROUP BY project_id
        LOOP
            IF rec.d_min IS NOT NULL AND rec.d_min <= cold_to AND rec.project_id IS NOT NULL THEN
                PERFORM fn_stats_users_daily_mark_dirty(
                    rec.project_id, rec.d_min - 1, LEAST(rec.d_max, cold_to)
                );
            END IF;
        END LOOP;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_server_traffic_stats_dirty_ins ON user_server_traffic;
DROP TRIGGER IF EXISTS trg_user_server_traffic_stats_dirty_upd ON user_server_traffic;
DROP TRIGGER IF EXISTS trg_user_server_traffic_stats_dirty_del ON user_server_traffic;

CREATE TRIGGER trg_user_server_traffic_stats_dirty_ins
AFTER INSERT ON user_server_traffic
REFERENCING NEW TABLE AS new_traffic
FOR EACH STATEMENT
EXECUTE FUNCTION trg_user_server_traffic_stats_dirty_stmt ();

CREATE TRIGGER trg_user_server_traffic_stats_dirty_upd
AFTER UPDATE ON user_server_traffic
REFERENCING OLD TABLE AS old_traffic NEW TABLE AS new_traffic
FOR EACH STATEMENT
EXECUTE FUNCTION trg_user_server_traffic_stats_dirty_stmt ();

CREATE TRIGGER trg_user_server_traffic_stats_dirty_del
AFTER DELETE ON user_server_traffic
REFERENCING OLD TABLE AS old_traffic
FOR EACH STATEMENT
EXECUTE FUNCTION trg_user_server_traffic_stats_dirty_stmt ();
