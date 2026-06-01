-- Сводка бухгалтерии (P&L) по месяцам в диапазоне [p_from, p_to] (по началу месяца).
-- Выручка — из payments (месяц created_at по календарю Москвы, как остальная stats-аналитика).
-- Расходы — разовые (expenses) плюс развёрнутые помесячно повторяющиеся шаблоны
-- (recurring_expenses). Налог и прибыль считаются в Python-сервисе по настройкам
-- (app_settings.finance). Все суммы — text (decimal).
DROP FUNCTION IF EXISTS rpc_finance_accounting_summary (date, date);

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
        date_trunc('month', p.created_at AT TIME ZONE 'Europe/Moscow')::date AS m_start,
        p.payment_kind,
        SUM(p.amount)::numeric(14, 2) AS gross,
        SUM(p.net_amount)::numeric(14, 2) AS net,
        COUNT(*)::bigint AS cnt
    FROM payments p
    WHERE date_trunc('month', p.created_at AT TIME ZONE 'Europe/Moscow')::date
          BETWEEN (SELECT m_from FROM bounds) AND (SELECT m_to FROM bounds)
    GROUP BY 1, 2
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
)
SELECT jsonb_build_object(
    'months',
    COALESCE((SELECT jsonb_agg(ym ORDER BY m_start) FROM months), '[]'::jsonb),
    'revenue_gross',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((SELECT SUM(gross) FROM pay p WHERE p.m_start = m.m_start), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'revenue_net',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((SELECT SUM(net) FROM pay p WHERE p.m_start = m.m_start), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'psp_commission',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((SELECT SUM(gross - net) FROM pay p WHERE p.m_start = m.m_start), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'revenue_gross_subscription',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((
                SELECT SUM(gross) FROM pay p
                WHERE p.m_start = m.m_start AND p.payment_kind = 'subscription'
            ), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'revenue_gross_one_time',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((
                SELECT SUM(gross) FROM pay p
                WHERE p.m_start = m.m_start AND p.payment_kind = 'one_time'
            ), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'expenses_total',
    COALESCE((
        SELECT jsonb_agg(
            COALESCE((SELECT SUM(amt) FROM exp_all ea WHERE ea.m_start = m.m_start), 0)::text
            ORDER BY m.m_start
        )
        FROM months m
    ), '[]'::jsonb),
    'expenses_by_category',
    COALESCE((
        SELECT jsonb_object_agg(
            s.slug,
            (
                SELECT jsonb_agg(
                    COALESCE((
                        SELECT amt FROM exp_by_slug e
                        WHERE e.slug = s.slug AND e.m_start = m.m_start
                    ), 0)::text
                    ORDER BY m.m_start
                )
                FROM months m
            )
        )
        FROM cat_slugs s
    ), '{}'::jsonb),
    'payment_count',
    COALESCE((SELECT SUM(cnt) FROM pay), 0)
);
$$;
