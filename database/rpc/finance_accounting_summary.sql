-- Сводка бухгалтерии (P&L) по месяцам в диапазоне [p_from, p_to].
CREATE OR REPLACE FUNCTION rpc_finance_accounting_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH bounds AS (
    SELECT
        date_trunc('month', p_from::timestamp)::date AS m_from,
        date_trunc('month', p_to::timestamp)::date AS m_to
),
months AS (
    SELECT
        to_char(gs, 'YYYY-MM') AS ym,
        gs::date AS m_start
    FROM bounds b
    CROSS JOIN LATERAL generate_series(
        b.m_from::timestamp,
        b.m_to::timestamp,
        interval '1 month'
    ) AS gs
),
pay AS (
    SELECT
        date_trunc('month', s.day_msk::timestamp)::date AS m_start,
        s.payment_kind,
        SUM(s.gross)::numeric(14, 2) AS gross,
        SUM(s.net)::numeric(14, 2) AS net,
        SUM(s.cnt)::bigint AS cnt
    FROM stats_payments_daily_msk s
    WHERE date_trunc('month', s.day_msk::timestamp)::date
          BETWEEN (SELECT m_from FROM bounds) AND (SELECT m_to FROM bounds)
    GROUP BY 1, 2
),
pay_monthly AS (
    SELECT
        m_start,
        COALESCE(SUM(gross), 0)::numeric(14, 2) AS gross_total,
        COALESCE(SUM(net), 0)::numeric(14, 2) AS net_total,
        COALESCE(SUM(gross) FILTER (WHERE payment_kind = 'subscription'), 0)::numeric(14, 2) AS gross_sub,
        COALESCE(SUM(gross) FILTER (WHERE payment_kind = 'one_time'), 0)::numeric(14, 2) AS gross_one,
        COALESCE(SUM(cnt), 0)::bigint AS cnt_total
    FROM pay
    GROUP BY m_start
),
exp_once AS (
    SELECT
        date_trunc('month', e.incurred_on)::date AS m_start,
        e.category_id,
        SUM(e.amount)::numeric(14, 2) AS amt
    FROM expenses e
    WHERE date_trunc('month', e.incurred_on)::date
          BETWEEN (SELECT m_from FROM bounds) AND (SELECT m_to FROM bounds)
    GROUP BY 1, 2
),
exp_recur AS (
    SELECT
        m.m_start,
        r.category_id,
        SUM(r.amount)::numeric(14, 2) AS amt
    FROM recurring_expenses r
    JOIN months m
        ON r.active = TRUE
        AND date_trunc('month', r.start_month)::date <= m.m_start
        AND (r.end_month IS NULL OR date_trunc('month', r.end_month)::date >= m.m_start)
    GROUP BY 1, 2
),
exp_all AS (
    SELECT m_start, category_id, SUM(amt)::numeric(14, 2) AS amt
    FROM (
        SELECT m_start, category_id, amt FROM exp_once
        UNION ALL
        SELECT m_start, category_id, amt FROM exp_recur
    ) u
    GROUP BY 1, 2
),
exp_monthly AS (
    SELECT m_start, COALESCE(SUM(amt), 0)::numeric(14, 2) AS expenses_total
    FROM exp_all
    GROUP BY m_start
),
exp_by_slug AS (
    SELECT
        COALESCE(c.slug, 'other') AS slug,
        ea.m_start,
        SUM(ea.amt)::numeric(14, 2) AS amt
    FROM exp_all ea
    LEFT JOIN expense_categories c ON c.id = ea.category_id
    GROUP BY 1, 2
),
cat_slugs AS (
    SELECT DISTINCT slug FROM exp_by_slug
),
month_joined AS (
    SELECT
        m.ym,
        m.m_start,
        COALESCE(pm.gross_total, 0)::text AS revenue_gross,
        COALESCE(pm.net_total, 0)::text AS revenue_net,
        COALESCE(pm.gross_total - pm.net_total, 0)::text AS psp_commission,
        COALESCE(pm.gross_sub, 0)::text AS revenue_gross_subscription,
        COALESCE(pm.gross_one, 0)::text AS revenue_gross_one_time,
        COALESCE(em.expenses_total, 0)::text AS expenses_total
    FROM months m
    LEFT JOIN pay_monthly pm ON pm.m_start = m.m_start
    LEFT JOIN exp_monthly em ON em.m_start = m.m_start
    ORDER BY m.m_start
),
cat_series AS (
    SELECT
        s.slug,
        jsonb_agg(
            COALESCE(ebs.amt, 0)::text
            ORDER BY m.m_start
        ) AS amounts
    FROM cat_slugs s
    CROSS JOIN months m
    LEFT JOIN exp_by_slug ebs
        ON ebs.slug = s.slug
       AND ebs.m_start = m.m_start
    GROUP BY s.slug
)
SELECT jsonb_build_object(
    'months',
    COALESCE((SELECT jsonb_agg(ym ORDER BY m_start) FROM months), '[]'::jsonb),
    'revenue_gross',
    COALESCE((SELECT jsonb_agg(revenue_gross) FROM month_joined), '[]'::jsonb),
    'revenue_net',
    COALESCE((SELECT jsonb_agg(revenue_net) FROM month_joined), '[]'::jsonb),
    'psp_commission',
    COALESCE((SELECT jsonb_agg(psp_commission) FROM month_joined), '[]'::jsonb),
    'revenue_gross_subscription',
    COALESCE((SELECT jsonb_agg(revenue_gross_subscription) FROM month_joined), '[]'::jsonb),
    'revenue_gross_one_time',
    COALESCE((SELECT jsonb_agg(revenue_gross_one_time) FROM month_joined), '[]'::jsonb),
    'expenses_total',
    COALESCE((SELECT jsonb_agg(expenses_total) FROM month_joined), '[]'::jsonb),
    'expenses_by_category',
    COALESCE((
        SELECT jsonb_object_agg(slug, amounts)
        FROM cat_series
    ), '{}'::jsonb),
    'payment_count',
    COALESCE((SELECT SUM(cnt_total) FROM pay_monthly), 0)
);
$$;
