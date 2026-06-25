-- Сводка платежей: календарные дни Europe/Moscow, суммы по payment_kind (net и gross).
-- Источник: stats_payments_daily_msk (триггер на payments).
CREATE OR REPLACE FUNCTION rpc_staff_payments_finance_summary_daily (
    p_from date DEFAULT NULL,
    p_to date DEFAULT NULL
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH filtered AS (
    SELECT
        s.day_msk,
        s.payment_kind,
        s.gross,
        s.net,
        s.cnt
    FROM stats_payments_daily_msk s
    WHERE (
        p_from IS NULL
        OR s.day_msk >= p_from
    )
    AND (
        p_to IS NULL
        OR s.day_msk <= p_to
    )
),
grand AS (
    SELECT
        COALESCE(SUM(net), 0)::numeric(14, 2) AS grand_total,
        COALESCE(SUM(gross), 0)::numeric(14, 2) AS grand_total_gross,
        COALESCE(SUM(cnt), 0)::bigint AS payment_count
    FROM filtered
),
agg_cash AS (
    SELECT
        to_char(day_msk, 'YYYY-MM-DD') AS ymd,
        payment_kind,
        SUM(net)::numeric(14, 2) AS total_amount
    FROM filtered
    GROUP BY 1, 2
),
agg_cash_gross AS (
    SELECT
        to_char(day_msk, 'YYYY-MM-DD') AS ymd,
        payment_kind,
        SUM(gross)::numeric(14, 2) AS total_amount
    FROM filtered
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
),
pivot_cash AS (
    SELECT
        dk.ymd,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_net,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_net
    FROM day_keys dk
    LEFT JOIN agg_cash a ON a.ymd = dk.ymd
    GROUP BY dk.ymd
    ORDER BY dk.ymd
),
pivot_cash_gross AS (
    SELECT
        dk.ymd,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'subscription'), 0)::text AS sub_gross,
        COALESCE(MAX(a.total_amount) FILTER (WHERE a.payment_kind = 'one_time'), 0)::text AS one_gross
    FROM day_keys dk
    LEFT JOIN agg_cash_gross a ON a.ymd = dk.ymd
    GROUP BY dk.ymd
    ORDER BY dk.ymd
)
SELECT jsonb_build_object(
    'days',
    COALESCE((SELECT jsonb_agg(ymd ORDER BY ymd) FROM day_keys), '[]'::jsonb),
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
    'grand_total',
    (SELECT grand_total::text FROM grand),
    'grand_total_gross',
    (SELECT grand_total_gross::text FROM grand),
    'payment_count',
    (SELECT payment_count FROM grand)
);
$$;
