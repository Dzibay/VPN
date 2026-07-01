-- Multi-tenant инкрементальные сводки платежей.
-- PK всех stats-таблиц включает project_id; триггер пишет OLD/NEW.project_id.

CREATE TABLE IF NOT EXISTS stats_payments_daily_utc (
    day_utc date NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 2) NOT NULL DEFAULT 0,
    net numeric(14, 2) NOT NULL DEFAULT 0,
    cnt bigint NOT NULL DEFAULT 0,
    CONSTRAINT stats_payments_daily_utc_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE TABLE IF NOT EXISTS stats_payments_daily_msk (
    day_msk date NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 2) NOT NULL DEFAULT 0,
    net numeric(14, 2) NOT NULL DEFAULT 0,
    cnt bigint NOT NULL DEFAULT 0,
    CONSTRAINT stats_payments_daily_msk_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

CREATE TABLE IF NOT EXISTS stats_payments_spread_monthly_utc (
    ym char(7) NOT NULL,
    payment_kind text NOT NULL,
    gross numeric(14, 6) NOT NULL DEFAULT 0,
    net numeric(14, 6) NOT NULL DEFAULT 0,
    CONSTRAINT stats_payments_spread_monthly_utc_kind CHECK (
        payment_kind IN ('subscription', 'one_time')
    )
);

DO $mig$
BEGIN
    -- stats_payments_daily_utc
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_payments_daily_utc' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_payments_daily_utc ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1
            REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE stats_payments_daily_utc ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_payments_daily_utc DROP CONSTRAINT IF EXISTS stats_payments_daily_utc_pkey;
        ALTER TABLE stats_payments_daily_utc
            ADD CONSTRAINT stats_payments_daily_utc_pkey
                PRIMARY KEY (project_id, day_utc, payment_kind);
    END IF;

    -- stats_payments_daily_msk
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_payments_daily_msk' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_payments_daily_msk ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1
            REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE stats_payments_daily_msk ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_payments_daily_msk DROP CONSTRAINT IF EXISTS stats_payments_daily_msk_pkey;
        ALTER TABLE stats_payments_daily_msk
            ADD CONSTRAINT stats_payments_daily_msk_pkey
                PRIMARY KEY (project_id, day_msk, payment_kind);
    END IF;

    -- stats_payments_spread_monthly_utc
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stats_payments_spread_monthly_utc' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE stats_payments_spread_monthly_utc ADD COLUMN project_id BIGINT NOT NULL DEFAULT 1
            REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE stats_payments_spread_monthly_utc ALTER COLUMN project_id DROP DEFAULT;
        ALTER TABLE stats_payments_spread_monthly_utc DROP CONSTRAINT IF EXISTS stats_payments_spread_monthly_utc_pkey;
        ALTER TABLE stats_payments_spread_monthly_utc
            ADD CONSTRAINT stats_payments_spread_monthly_utc_pkey
                PRIMARY KEY (project_id, ym, payment_kind);
    END IF;
END $mig$;

CREATE INDEX IF NOT EXISTS idx_stats_payments_daily_utc_day
    ON stats_payments_daily_utc (day_utc);

CREATE INDEX IF NOT EXISTS idx_stats_payments_daily_msk_day
    ON stats_payments_daily_msk (day_msk);

CREATE OR REPLACE FUNCTION fn_payments_rollup_apply_row (
    p_row payments,
    p_sign integer
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    d_utc date;
    d_msk date;
    gross_delta numeric(14, 2);
    net_delta numeric(14, 2);
    cnt_delta bigint;
    n integer;
    v_ym text;
    part_gross numeric(14, 6);
    part_net numeric(14, 6);
    pid bigint;
BEGIN
    IF p_sign = 0 OR p_row IS NULL THEN
        RETURN;
    END IF;
    pid := p_row.project_id;
    IF pid IS NULL THEN
        RAISE EXCEPTION 'fn_payments_rollup_apply_row: payments.project_id NULL (id=%)', p_row.id;
    END IF;

    d_utc := (p_row.created_at AT TIME ZONE 'UTC')::date;
    d_msk := (p_row.created_at AT TIME ZONE 'Europe/Moscow')::date;
    gross_delta := (p_row.amount * p_sign)::numeric(14, 2);
    net_delta := (p_row.net_amount * p_sign)::numeric(14, 2);
    cnt_delta := p_sign::bigint;

    INSERT INTO stats_payments_daily_utc (project_id, day_utc, payment_kind, gross, net, cnt)
    VALUES (pid, d_utc, p_row.payment_kind, gross_delta, net_delta, cnt_delta)
    ON CONFLICT (project_id, day_utc, payment_kind) DO UPDATE
    SET
        gross = stats_payments_daily_utc.gross + EXCLUDED.gross,
        net = stats_payments_daily_utc.net + EXCLUDED.net,
        cnt = stats_payments_daily_utc.cnt + EXCLUDED.cnt;

    INSERT INTO stats_payments_daily_msk (project_id, day_msk, payment_kind, gross, net, cnt)
    VALUES (pid, d_msk, p_row.payment_kind, gross_delta, net_delta, cnt_delta)
    ON CONFLICT (project_id, day_msk, payment_kind) DO UPDATE
    SET
        gross = stats_payments_daily_msk.gross + EXCLUDED.gross,
        net = stats_payments_daily_msk.net + EXCLUDED.net,
        cnt = stats_payments_daily_msk.cnt + EXCLUDED.cnt;

    IF p_row.months > 0 THEN
        part_gross := (p_row.amount / p_row.months::numeric) * p_sign;
        part_net := (p_row.net_amount / p_row.months::numeric) * p_sign;
        FOR n IN 0..(p_row.months - 1) LOOP
            v_ym := to_char(
                date_trunc('month', p_row.created_at AT TIME ZONE 'UTC')
                + (n || ' months')::interval,
                'YYYY-MM'
            );
            INSERT INTO stats_payments_spread_monthly_utc (project_id, ym, payment_kind, gross, net)
            VALUES (pid, v_ym, p_row.payment_kind, part_gross, part_net)
            ON CONFLICT (project_id, ym, payment_kind) DO UPDATE
            SET
                gross = stats_payments_spread_monthly_utc.gross + EXCLUDED.gross,
                net = stats_payments_spread_monthly_utc.net + EXCLUDED.net;
        END LOOP;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION trg_payments_rollup ()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_payments_rollup_apply_row(OLD, -1);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM fn_payments_rollup_apply_row(OLD, -1);
        PERFORM fn_payments_rollup_apply_row(NEW, 1);
        RETURN NEW;
    END IF;

    PERFORM fn_payments_rollup_apply_row(NEW, 1);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_payments_rollup ON payments;

CREATE TRIGGER trg_payments_rollup
AFTER INSERT OR UPDATE OR DELETE ON payments
FOR EACH ROW
EXECUTE FUNCTION trg_payments_rollup();

-- Начальный backfill только если stats пусты (multi-tenant: сразу с project_id).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM stats_payments_daily_utc LIMIT 1) THEN
        RETURN;
    END IF;

    INSERT INTO stats_payments_daily_utc (project_id, day_utc, payment_kind, gross, net, cnt)
    SELECT
        p.project_id,
        (p.created_at AT TIME ZONE 'UTC')::date AS day_utc,
        p.payment_kind,
        COALESCE(SUM(p.amount), 0)::numeric(14, 2),
        COALESCE(SUM(p.net_amount), 0)::numeric(14, 2),
        COUNT(*)::bigint
    FROM payments p
    GROUP BY 1, 2, 3;

    INSERT INTO stats_payments_daily_msk (project_id, day_msk, payment_kind, gross, net, cnt)
    SELECT
        p.project_id,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS day_msk,
        p.payment_kind,
        COALESCE(SUM(p.amount), 0)::numeric(14, 2),
        COALESCE(SUM(p.net_amount), 0)::numeric(14, 2),
        COUNT(*)::bigint
    FROM payments p
    GROUP BY 1, 2, 3;

    INSERT INTO stats_payments_spread_monthly_utc (project_id, ym, payment_kind, gross, net)
    SELECT
        p.project_id,
        to_char(
            date_trunc('month', p.created_at AT TIME ZONE 'UTC')
            + (gs.n || ' months')::interval,
            'YYYY-MM'
        ) AS ym,
        p.payment_kind,
        SUM(p.amount / p.months::numeric)::numeric(14, 6),
        SUM(p.net_amount / p.months::numeric)::numeric(14, 6)
    FROM payments p
    CROSS JOIN LATERAL generate_series(0, p.months - 1) AS gs (n)
    WHERE p.months > 0
    GROUP BY 1, 2, 3;
END;
$$;
