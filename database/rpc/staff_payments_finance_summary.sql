-- Сводка платежей: месяцы UTC, суммы по payment_kind (net и gross).
-- p_from / p_to — опциональный диапазон календарных дней UTC (включительно); NULL = вся история.
DROP FUNCTION IF EXISTS rpc_staff_payments_finance_summary ();

DROP FUNCTION IF EXISTS rpc_staff_payments_finance_summary (date, date);

CREATE OR REPLACE FUNCTION rpc_staff_payments_finance_summary (
    p_from date DEFAULT NULL,
    p_to date DEFAULT NULL
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH filtered AS (
    SELECT *
    FROM payments p
    WHERE (
        p_from IS NULL
        OR (p.created_at AT TIME ZONE 'UTC')::date >= p_from
    )
    AND (
        p_to IS NULL
        OR (p.created_at AT TIME ZONE 'UTC')::date <= p_to
    )
),
grand AS (
    SELECT
        COALESCE(SUM(net_amount), 0)::numeric(14, 2) AS grand_total,
        COALESCE(SUM(amount), 0)::numeric(14, 2) AS grand_total_gross,
        COUNT(*)::bigint AS payment_count
    FROM filtered
),
agg_cash AS (
    SELECT
        to_char(date_trunc('month', created_at AT TIME ZONE 'UTC'), 'YYYY-MM') AS ym,
        payment_kind,
        SUM(net_amount)::numeric(14, 2) AS total_amount
    FROM filtered
    GROUP BY 1, 2
),
agg_cash_gross AS (
    SELECT
        to_char(date_trunc('month', created_at AT TIME ZONE 'UTC'), 'YYYY-MM') AS ym,
        payment_kind,
        SUM(amount)::numeric(14, 2) AS total_amount
    FROM filtered
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
        (p.net_amount / p.months::numeric)::numeric(14, 6) AS part_amt,
        (p.amount / p.months::numeric)::numeric(14, 6) AS part_amt_gross
    FROM filtered p
    CROSS JOIN LATERAL generate_series(0, p.months - 1) AS gs (n)
),
agg_spread AS (
    SELECT
        sp.ym,
        sp.payment_kind,
        SUM(sp.part_amt)::numeric(14, 2) AS total_amount
    FROM spread_parts sp
    WHERE (
        p_from IS NULL
        OR sp.ym >= to_char(date_trunc('month', p_from::timestamp), 'YYYY-MM')
    )
    AND (
        p_to IS NULL
        OR sp.ym <= to_char(date_trunc('month', p_to::timestamp), 'YYYY-MM')
    )
    GROUP BY 1, 2
),
agg_spread_gross AS (
    SELECT
        sp.ym,
        sp.payment_kind,
        SUM(sp.part_amt_gross)::numeric(14, 2) AS total_amount
    FROM spread_parts sp
    WHERE (
        p_from IS NULL
        OR sp.ym >= to_char(date_trunc('month', p_from::timestamp), 'YYYY-MM')
    )
    AND (
        p_to IS NULL
        OR sp.ym <= to_char(date_trunc('month', p_to::timestamp), 'YYYY-MM')
    )
    GROUP BY 1, 2
),
all_ym AS (
    SELECT ym FROM agg_cash
    UNION
    SELECT ym FROM agg_cash_gross
    UNION
    SELECT ym FROM agg_spread
    UNION
    SELECT ym FROM agg_spread_gross
),
month_keys AS (
    SELECT ym
    FROM all_ym
    ORDER BY ym
),
pivot_cash AS (
    SELECT
        mk.ym,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_net,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_net
    FROM month_keys mk
    LEFT JOIN agg_cash a ON a.ym = mk.ym
    GROUP BY mk.ym
    ORDER BY mk.ym
),
pivot_cash_gross AS (
    SELECT
        mk.ym,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_gross,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_gross
    FROM month_keys mk
    LEFT JOIN agg_cash_gross a ON a.ym = mk.ym
    GROUP BY mk.ym
    ORDER BY mk.ym
),
pivot_spread AS (
    SELECT
        mk.ym,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_net,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_net
    FROM month_keys mk
    LEFT JOIN agg_spread a ON a.ym = mk.ym
    GROUP BY mk.ym
    ORDER BY mk.ym
),
pivot_spread_gross AS (
    SELECT
        mk.ym,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_gross,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_gross
    FROM month_keys mk
    LEFT JOIN agg_spread_gross a ON a.ym = mk.ym
    GROUP BY mk.ym
    ORDER BY mk.ym
)
SELECT jsonb_build_object(
    'months',
    COALESCE((SELECT jsonb_agg(ym ORDER BY ym) FROM month_keys), '[]'::jsonb),
    'cash',
    jsonb_build_object(
        'subscription',
        COALESCE((SELECT jsonb_agg(sub_net) FROM pivot_cash), '[]'::jsonb),
        'one_time',
        COALESCE((SELECT jsonb_agg(one_net) FROM pivot_cash), '[]'::jsonb)
    ),
    'cash_gross',
    jsonb_build_object(
        'subscription',
        COALESCE((SELECT jsonb_agg(sub_gross) FROM pivot_cash_gross), '[]'::jsonb),
        'one_time',
        COALESCE((SELECT jsonb_agg(one_gross) FROM pivot_cash_gross), '[]'::jsonb)
    ),
    'spread',
    jsonb_build_object(
        'subscription',
        COALESCE((SELECT jsonb_agg(sub_net) FROM pivot_spread), '[]'::jsonb),
        'one_time',
        COALESCE((SELECT jsonb_agg(one_net) FROM pivot_spread), '[]'::jsonb)
    ),
    'spread_gross',
    jsonb_build_object(
        'subscription',
        COALESCE((SELECT jsonb_agg(sub_gross) FROM pivot_spread_gross), '[]'::jsonb),
        'one_time',
        COALESCE((SELECT jsonb_agg(one_gross) FROM pivot_spread_gross), '[]'::jsonb)
    ),
    'grand_total',
    (SELECT grand_total::text FROM grand),
    'grand_total_gross',
    (SELECT grand_total_gross::text FROM grand),
    'payment_count',
    (SELECT payment_count FROM grand)
);
$$;
