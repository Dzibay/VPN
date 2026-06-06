-- Сводка платежей: календарные дни UTC, суммы по payment_kind (net и gross).
-- cash — вся сумма в день даты платежа (аналог monthly cash, но по дням).
DROP FUNCTION IF EXISTS rpc_staff_payments_finance_summary_daily;

CREATE OR REPLACE FUNCTION rpc_staff_payments_finance_summary_daily ()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH grand AS (
    SELECT
        COALESCE(SUM(net_amount), 0)::numeric(14, 2) AS grand_total,
        COALESCE(SUM(amount), 0)::numeric(14, 2) AS grand_total_gross,
        COUNT(*)::bigint AS payment_count
    FROM payments
),
agg_cash AS (
    SELECT
        to_char(date_trunc('day', created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS ymd,
        payment_kind,
        SUM(net_amount)::numeric(14, 2) AS total_amount
    FROM payments
    GROUP BY 1, 2
),
agg_cash_gross AS (
    SELECT
        to_char(date_trunc('day', created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS ymd,
        payment_kind,
        SUM(amount)::numeric(14, 2) AS total_amount
    FROM payments
    GROUP BY 1, 2
),
all_ymd AS (
    SELECT ymd FROM agg_cash
    UNION
    SELECT ymd FROM agg_cash_gross
),
day_keys AS (
    SELECT ymd
    FROM all_ymd
    ORDER BY ymd
)
SELECT jsonb_build_object(
    'days',
    COALESCE((SELECT jsonb_agg(ymd ORDER BY ymd) FROM day_keys), '[]'::jsonb),
    'cash',
    jsonb_build_object(
        'subscription',
        COALESCE(
            (
                SELECT jsonb_agg(
                    COALESCE(
                        (
                            SELECT a.total_amount::text
                            FROM agg_cash a
                            WHERE a.ymd = dk.ymd
                              AND a.payment_kind = 'subscription'
                        ),
                        '0'
                    )
                    ORDER BY dk.ymd
                )
                FROM day_keys dk
            ),
            '[]'::jsonb
        ),
        'one_time',
        COALESCE(
            (
                SELECT jsonb_agg(
                    COALESCE(
                        (
                            SELECT a.total_amount::text
                            FROM agg_cash a
                            WHERE a.ymd = dk.ymd
                              AND a.payment_kind = 'one_time'
                        ),
                        '0'
                    )
                    ORDER BY dk.ymd
                )
                FROM day_keys dk
            ),
            '[]'::jsonb
        )
    ),
    'cash_gross',
    jsonb_build_object(
        'subscription',
        COALESCE(
            (
                SELECT jsonb_agg(
                    COALESCE(
                        (
                            SELECT a.total_amount::text
                            FROM agg_cash_gross a
                            WHERE a.ymd = dk.ymd
                              AND a.payment_kind = 'subscription'
                        ),
                        '0'
                    )
                    ORDER BY dk.ymd
                )
                FROM day_keys dk
            ),
            '[]'::jsonb
        ),
        'one_time',
        COALESCE(
            (
                SELECT jsonb_agg(
                    COALESCE(
                        (
                            SELECT a.total_amount::text
                            FROM agg_cash_gross a
                            WHERE a.ymd = dk.ymd
                              AND a.payment_kind = 'one_time'
                        ),
                        '0'
                    )
                    ORDER BY dk.ymd
                )
                FROM day_keys dk
            ),
            '[]'::jsonb
        )
    ),
    'grand_total',
    (SELECT grand_total::text FROM grand),
    'grand_total_gross',
    (SELECT grand_total_gross::text FROM grand),
    'payment_count',
    (SELECT payment_count FROM grand)
);
$$;
