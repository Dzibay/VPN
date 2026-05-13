-- Сводка платежей: месяцы UTC, суммы по payment_kind.
-- cash — вся сумма в месяце даты платежа.
-- spread — сумма / months в месяце платежа и в каждом из следующих (months-1) месяцев UTC.
DROP FUNCTION IF EXISTS rpc_staff_payments_finance_summary;

CREATE OR REPLACE FUNCTION rpc_staff_payments_finance_summary ()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH grand AS (
    SELECT
        COALESCE(SUM(amount), 0)::numeric(14, 2) AS grand_total,
        COUNT(*)::bigint AS payment_count
    FROM payments
),
agg_cash AS (
    SELECT
        to_char(date_trunc('month', created_at AT TIME ZONE 'UTC'), 'YYYY-MM') AS ym,
        payment_kind,
        SUM(amount)::numeric(14, 2) AS total_amount
    FROM payments
    GROUP BY 1, 2
),
spread_parts AS (
    SELECT
        to_char(
            date_trunc('month', p.created_at AT TIME ZONE 'UTC')
            + (gs.n || ' months')::interval,
            'YYYY-MM'
        ) AS ym,
        p.payment_kind,
        (p.amount / p.months::numeric)::numeric(14, 6) AS part_amt
    FROM payments p
    CROSS JOIN LATERAL generate_series(0, p.months - 1) AS gs (n)
),
agg_spread AS (
    SELECT
        ym,
        payment_kind,
        SUM(part_amt)::numeric(14, 2) AS total_amount
    FROM spread_parts
    GROUP BY 1, 2
),
all_ym AS (
    SELECT ym FROM agg_cash
    UNION
    SELECT ym FROM agg_spread
),
month_keys AS (
    SELECT ym
    FROM all_ym
    ORDER BY ym
)
SELECT jsonb_build_object(
    'months',
    COALESCE((SELECT jsonb_agg(ym ORDER BY ym) FROM month_keys), '[]'::jsonb),
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
                            WHERE a.ym = mk.ym
                              AND a.payment_kind = 'subscription'
                        ),
                        '0'
                    )
                    ORDER BY mk.ym
                )
                FROM month_keys mk
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
                            WHERE a.ym = mk.ym
                              AND a.payment_kind = 'one_time'
                        ),
                        '0'
                    )
                    ORDER BY mk.ym
                )
                FROM month_keys mk
            ),
            '[]'::jsonb
        )
    ),
    'spread',
    jsonb_build_object(
        'subscription',
        COALESCE(
            (
                SELECT jsonb_agg(
                    COALESCE(
                        (
                            SELECT a.total_amount::text
                            FROM agg_spread a
                            WHERE a.ym = mk.ym
                              AND a.payment_kind = 'subscription'
                        ),
                        '0'
                    )
                    ORDER BY mk.ym
                )
                FROM month_keys mk
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
                            FROM agg_spread a
                            WHERE a.ym = mk.ym
                              AND a.payment_kind = 'one_time'
                        ),
                        '0'
                    )
                    ORDER BY mk.ym
                )
                FROM month_keys mk
            ),
            '[]'::jsonb
        )
    ),
    'grand_total',
    (SELECT grand_total::text FROM grand),
    'payment_count',
    (SELECT payment_count FROM grand)
);
$$;
