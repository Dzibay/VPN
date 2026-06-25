-- Умный кэш stats_users_daily_msk: очередь «грязных» холодных дней + триггеры на источники.
-- «Горячее» окно (последние N дней МСК) всегда считается на чтении в rpc_users_daily_stats.

CREATE TABLE IF NOT EXISTS stats_users_daily_dirty (
    stats_date date PRIMARY KEY,
    dirty_at timestamptz NOT NULL DEFAULT now()
);

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

    INSERT INTO stats_users_daily_dirty (stats_date)
    SELECT gs::date
    FROM generate_series(d_from, d_to, interval '1 day') AS gs
    ON CONFLICT (stats_date) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_mark_recent_cold_dirty (
    p_days integer DEFAULT 90
)
RETURNS void
LANGUAGE sql
SET search_path TO public
AS $$
SELECT fn_stats_users_daily_mark_dirty(
    fn_stats_users_daily_hot_start() - GREATEST(p_days, 1),
    fn_stats_users_daily_hot_start() - 1
);
$$;

CREATE OR REPLACE FUNCTION fn_stats_users_daily_dirty_count ()
RETURNS bigint
LANGUAGE sql
STABLE
SET search_path TO public
AS $$
SELECT COUNT(*)::bigint FROM stats_users_daily_dirty;
$$;

-- fn_stats_users_daily_flush_dirty — в post_users_daily_stats_mv.sql (после compute).

-- --- триггеры ---

-- Триггер на users: помечаем только ХОЛОДНЫЕ дни. Горячее окно всегда live-compute,
-- поэтому пометки внутри него — пустая работа.
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
BEGIN
    IF TG_OP = 'DELETE' THEN
        candidates := ARRAY[
            CASE WHEN OLD.registered_at IS NOT NULL
                 THEN (OLD.registered_at AT TIME ZONE 'Europe/Moscow')::date END,
            CASE WHEN OLD.subscription_until IS NOT NULL
                 THEN OLD.subscription_until::date + 1 END
        ];
    ELSE
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

    IF d_from IS NOT NULL THEN
        PERFORM fn_stats_users_daily_mark_dirty(d_from, d_to);
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
BEGIN
    IF TG_OP = 'DELETE' THEN
        d_old := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
        IF d_old <= cold_to THEN
            PERFORM fn_stats_users_daily_mark_dirty(d_old, d_old);
        END IF;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        d_old := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
        d_new := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
        d_from := LEAST(d_old, d_new);
        d_to := LEAST(GREATEST(d_old, d_new), cold_to);
        IF d_from <= cold_to THEN
            PERFORM fn_stats_users_daily_mark_dirty(d_from, d_to);
        END IF;
        RETURN NEW;
    END IF;

    d_new := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
    IF d_new <= cold_to THEN
        PERFORM fn_stats_users_daily_mark_dirty(d_new, d_new);
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
BEGIN
    IF TG_OP = 'DELETE' THEN
        d_day := (OLD.created_at AT TIME ZONE 'Europe/Moscow')::date;
    ELSE
        d_day := (NEW.created_at AT TIME ZONE 'Europe/Moscow')::date;
    END IF;

    IF d_day <= cold_to THEN
        PERFORM fn_stats_users_daily_mark_dirty(d_day, d_day);
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

-- Триггер на трафик: мы метим dirty только ХОЛОДНЫЕ дни.
-- Горячее окно всегда live-compute, его пометки бесполезны и расточительны.
-- Большая часть трафика пишется за вчера/сегодня → попадает в горячее окно
-- → trg вообще ничего не помечает. mark_dirty внутри уже отфильтровывает
-- > cold_to, но мы дополнительно избегаем вызова функции через быструю проверку.
CREATE OR REPLACE FUNCTION trg_user_server_traffic_stats_dirty_stmt ()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    d_min date;
    d_max date;
    cold_to date;
BEGIN
    cold_to := fn_stats_users_daily_hot_start() - 1;

    IF TG_OP = 'DELETE' THEN
        SELECT MIN(traffic_date), MAX(traffic_date)
        INTO d_min, d_max
        FROM old_traffic;
    ELSE
        SELECT MIN(traffic_date), MAX(traffic_date)
        INTO d_min, d_max
        FROM new_traffic;
    END IF;

    -- ничего нового или всё в горячем окне → нечего помечать
    IF d_min IS NULL OR d_min > cold_to THEN
        RETURN NULL;
    END IF;

    -- Расширяем на один день вниз: LAG берёт предыдущий снимок.
    PERFORM fn_stats_users_daily_mark_dirty(
        d_min - 1,
        LEAST(d_max, cold_to)
    );
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
