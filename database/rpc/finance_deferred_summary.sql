-- Признание выручки помесячно от даты платежа и баланс обязательств («замороженные деньги»).
--
-- Платежи с months > 0: каждая «годовщина» даты оплаты (15 мая → 15 июня, 15 июля …)
-- размораживает 1/months суммы. 1 месяц → 15 июня 100%; 3 месяца → 15 июня 33%, 15 авг. 100%.
-- Разовые (months=0) — сразу в дату платежа.
DROP FUNCTION IF EXISTS rpc_finance_deferred_summary (date, date);

CREATE OR REPLACE FUNCTION rpc_finance_deferred_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH params AS (
    SELECT
        p_from AS range_from,
        p_to AS range_to,
        date_trunc('month', p_from::timestamp)::date AS m_from,
        date_trunc('month', p_to::timestamp)::date AS m_to,
        LEAST(
            p_to,
            (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date
        ) AS as_of,
        GREATEST(
            p_to,
            (
                LEAST(
                    p_to,
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date
                ) + interval '24 months'
            )::date
        ) AS unlock_horizon
),
pp AS (
    SELECT
        p.id,
        p.amount AS gross,
        p.net_amount AS net,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS s_day,
        (p.months > 0) AS is_sub,
        p.months AS pay_months
    FROM payments p
),
m AS (
    SELECT
        gs::date AS m_start,
        LEAST(
            (gs + interval '1 month - 1 day')::date,
            (SELECT as_of FROM params)
        ) AS m_end
    FROM generate_series(
        (SELECT m_from FROM params)::timestamp,
        (SELECT m_to FROM params)::timestamp,
        interval '1 month'
    ) AS gs
),
eval_points AS (
    SELECT as_of AS eval_d FROM params
    UNION
    SELECT m_end FROM m
    UNION
    SELECT (m_start - 1)::date FROM m
),
thaw_frac AS (
    SELECT
        pp.id,
        pp.gross,
        pp.net,
        pp.s_day,
        pp.is_sub,
        pp.pay_months,
        ep.eval_d,
        CASE
            WHEN NOT pp.is_sub
                THEN CASE WHEN pp.s_day <= ep.eval_d THEN 1::numeric ELSE 0::numeric END
            ELSE LEAST(
                COALESCE((
                    SELECT COUNT(*)::numeric
                    FROM generate_series(1, pp.pay_months) AS n(n)
                    WHERE (pp.s_day + (n || ' months')::interval)::date <= ep.eval_d
                ), 0) / pp.pay_months::numeric,
                1::numeric
            )
        END AS frac
    FROM pp
    CROSS JOIN eval_points ep
),
base AS (
    SELECT
        m.m_start,
        pp.net,
        pp.gross,
        fe.frac AS fe,
        fs.frac AS fs
    FROM m
    INNER JOIN pp ON pp.s_day <= m.m_end
    INNER JOIN thaw_frac fe ON fe.id = pp.id AND fe.eval_d = m.m_end
    INNER JOIN thaw_frac fs ON fs.id = pp.id AND fs.eval_d = (m.m_start - 1)
    WHERE fe.frac > fs.frac OR fe.frac < 1::numeric
),
per_month AS (
    SELECT
        m_start,
        SUM(net * (fe - fs))::numeric(14, 2) AS earned_net,
        SUM(gross * (fe - fs))::numeric(14, 2) AS earned_gross,
        SUM(net * (1 - fe))::numeric(14, 2) AS deferred_net,
        SUM(gross * (1 - fe))::numeric(14, 2) AS deferred_gross
    FROM base
    GROUP BY m_start
),
snap_raw AS (
    SELECT
        SUM(CASE WHEN tf.s_day <= tf.eval_d THEN tf.net ELSE 0 END)::numeric(14, 2) AS received_net,
        SUM(CASE WHEN tf.s_day <= tf.eval_d THEN tf.gross ELSE 0 END)::numeric(14, 2) AS received_gross,
        SUM(tf.net * tf.frac)::numeric(14, 2) AS earned_net_raw,
        SUM(tf.gross * tf.frac)::numeric(14, 2) AS earned_gross_raw
    FROM thaw_frac tf
    WHERE tf.eval_d = (SELECT as_of FROM params)
),
snap AS (
    SELECT
        received_net,
        received_gross,
        LEAST(earned_net_raw, received_net)::numeric(14, 2) AS earned_net,
        LEAST(earned_gross_raw, received_gross)::numeric(14, 2) AS earned_gross
    FROM snap_raw
),
active_paid AS (
    SELECT COUNT(DISTINCT u.id)::bigint AS cnt
    FROM users u
    CROSS JOIN params pr
    WHERE (u.subscription_until IS NULL OR u.subscription_until >= pr.as_of)
      AND EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.user_id = u.id
            AND p.months > 0
      )
),
unlock_chunks AS (
    SELECT
        (pp.s_day + (n || ' months')::interval)::date AS unlock_day,
        (pp.net / pp.pay_months::numeric)::numeric(14, 6) AS chunk_net
    FROM pp
    CROSS JOIN generate_series(1, pp.pay_months) AS n(n)
    CROSS JOIN params pr
    WHERE pp.is_sub AND pp.s_day <= pr.as_of

    UNION ALL

    SELECT pp.s_day, pp.net
    FROM pp
    CROSS JOIN params pr
    WHERE NOT pp.is_sub AND pp.s_day <= pr.as_of
),
unlock_daily AS (
    SELECT
        uc.unlock_day,
        SUM(uc.chunk_net)::numeric(14, 2) AS amount_net
    FROM unlock_chunks uc
    CROSS JOIN params pr
    WHERE uc.unlock_day >= pr.range_from
      AND uc.unlock_day <= pr.unlock_horizon
    GROUP BY uc.unlock_day
),
unlock_monthly AS (
    SELECT
        date_trunc('month', ud.unlock_day)::date AS m_start,
        SUM(ud.amount_net)::numeric(14, 2) AS amount_net
    FROM unlock_daily ud
    GROUP BY 1
)
SELECT jsonb_build_object(
    'months',
    COALESCE((SELECT jsonb_agg(to_char(m_start, 'YYYY-MM') ORDER BY m_start) FROM m), '[]'::jsonb),
    'earned_net',
    COALESCE((
        SELECT jsonb_agg(COALESCE(pm.earned_net, 0)::text ORDER BY m.m_start)
        FROM m LEFT JOIN per_month pm ON pm.m_start = m.m_start
    ), '[]'::jsonb),
    'earned_gross',
    COALESCE((
        SELECT jsonb_agg(COALESCE(pm.earned_gross, 0)::text ORDER BY m.m_start)
        FROM m LEFT JOIN per_month pm ON pm.m_start = m.m_start
    ), '[]'::jsonb),
    'deferred_net_end',
    COALESCE((
        SELECT jsonb_agg(COALESCE(pm.deferred_net, 0)::text ORDER BY m.m_start)
        FROM m LEFT JOIN per_month pm ON pm.m_start = m.m_start
    ), '[]'::jsonb),
    'deferred_gross_end',
    COALESCE((
        SELECT jsonb_agg(COALESCE(pm.deferred_gross, 0)::text ORDER BY m.m_start)
        FROM m LEFT JOIN per_month pm ON pm.m_start = m.m_start
    ), '[]'::jsonb),
    'snapshot',
    jsonb_build_object(
        'as_of', to_char((SELECT as_of FROM params), 'YYYY-MM-DD'),
        'received_net', COALESCE((SELECT received_net FROM snap), 0)::text,
        'received_gross', COALESCE((SELECT received_gross FROM snap), 0)::text,
        'earned_net', COALESCE((SELECT earned_net FROM snap), 0)::text,
        'earned_gross', COALESCE((SELECT earned_gross FROM snap), 0)::text,
        'deferred_net', COALESCE((
            SELECT GREATEST(received_net - earned_net, 0) FROM snap
        ), 0)::text,
        'deferred_gross', COALESCE((
            SELECT GREATEST(received_gross - earned_gross, 0) FROM snap
        ), 0)::text,
        'active_obligations', COALESCE((SELECT cnt FROM active_paid), 0)
    ),
    'unlock',
    jsonb_build_object(
        'days',
        COALESCE((
            SELECT jsonb_agg(to_char(unlock_day, 'YYYY-MM-DD') ORDER BY unlock_day)
            FROM unlock_daily
        ), '[]'::jsonb),
        'amounts_net',
        COALESCE((
            SELECT jsonb_agg(amount_net::text ORDER BY unlock_day)
            FROM unlock_daily
        ), '[]'::jsonb),
        'months',
        COALESCE((
            SELECT jsonb_agg(to_char(m_start, 'YYYY-MM') ORDER BY m_start)
            FROM unlock_monthly
        ), '[]'::jsonb),
        'amounts_net_monthly',
        COALESCE((
            SELECT jsonb_agg(amount_net::text ORDER BY m_start)
            FROM unlock_monthly
        ), '[]'::jsonb)
    )
);
$$;
