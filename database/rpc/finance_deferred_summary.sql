-- Признание выручки по дням и баланс неисполненных обязательств («замороженные деньги»).
--
-- Подписка на `months` покрывает `months * 31` дней с даты платежа (DAYS_PER_MONTH=31,
-- см. payment_service.py). Выручка «зарабатывается» равномерно по дням этого периода:
--   earned(X) = amount * clamp((X - start_day) / total_days, 0, 1)
-- Разовые платежи (one_time) зарабатываются сразу в дату платежа (обязательств нет).
--
-- Это точнее «по месяцам оплаты» (spread): платёж 30 мая даёт за май лишь ~2 дня выручки,
-- остальное переносится на следующие месяцы по факту прошедших дней.
--
-- На выходе помесячно (UTC) в диапазоне [p_from, p_to]:
--   earned_net[]/earned_gross[]        — признанная выручка за месяц (поток);
--   deferred_net_end[]/deferred_gross_end[] — остаток обязательств на конец месяца (запас);
-- плюс snapshot на момент p_to: поступило / заработано (свободно) / заморожено.
DROP FUNCTION IF EXISTS rpc_finance_deferred_summary (date, date);

CREATE OR REPLACE FUNCTION rpc_finance_deferred_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH params AS (
    SELECT
        date_trunc('month', p_from::timestamp)::date AS m_from,
        date_trunc('month', p_to::timestamp)::date AS m_to,
        (p_to + 1) AS x_now  -- эксклюзивная верхняя граница «сейчас» (конец дня p_to)
),
m AS (
    SELECT
        gs::date AS m_start,
        (gs + interval '1 month')::date AS m_next,
        -- точка оценки: конец месяца, но не дальше «сейчас» (для текущего месяца — сегодня)
        LEAST((gs + interval '1 month')::date, (SELECT x_now FROM params)) AS xe
    FROM generate_series(
        (SELECT m_from FROM params)::timestamp,
        (SELECT m_to FROM params)::timestamp,
        interval '1 month'
    ) AS gs
),
pp AS (
    SELECT
        p.amount AS gross,
        p.net_amount AS net,
        (p.created_at AT TIME ZONE 'UTC')::date AS s_day,
        (p.payment_kind = 'subscription' AND p.months > 0) AS is_sub,
        (p.months * 31) AS dur
    FROM payments p
),
base AS (
    SELECT
        m.m_start,
        pp.net,
        pp.gross,
        -- доля признанной выручки на конец месяца (xe)
        CASE
            WHEN pp.is_sub
                THEN LEAST(GREATEST((m.xe - pp.s_day), 0), pp.dur)::numeric / pp.dur
            ELSE CASE WHEN pp.s_day < m.xe THEN 1 ELSE 0 END
        END AS fe,
        -- доля признанной выручки на начало месяца (m_start)
        CASE
            WHEN pp.is_sub
                THEN LEAST(GREATEST((m.m_start - pp.s_day), 0), pp.dur)::numeric / pp.dur
            ELSE CASE WHEN pp.s_day < m.m_start THEN 1 ELSE 0 END
        END AS fs
    FROM m
    JOIN pp ON (
        (pp.is_sub AND pp.s_day < m.xe AND (pp.s_day + pp.dur) > m.m_start)
        OR (NOT pp.is_sub AND pp.s_day >= m.m_start AND pp.s_day < m.xe)
    )
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
snap AS (
    SELECT
        SUM(CASE WHEN pp.s_day < pr.x_now THEN pp.net ELSE 0 END)::numeric(14, 2) AS received_net,
        SUM(CASE WHEN pp.s_day < pr.x_now THEN pp.gross ELSE 0 END)::numeric(14, 2) AS received_gross,
        SUM(
            pp.net * CASE
                WHEN pp.is_sub
                    THEN LEAST(GREATEST((pr.x_now - pp.s_day), 0), pp.dur)::numeric / pp.dur
                ELSE CASE WHEN pp.s_day < pr.x_now THEN 1 ELSE 0 END
            END
        )::numeric(14, 2) AS earned_net,
        SUM(
            pp.gross * CASE
                WHEN pp.is_sub
                    THEN LEAST(GREATEST((pr.x_now - pp.s_day), 0), pp.dur)::numeric / pp.dur
                ELSE CASE WHEN pp.s_day < pr.x_now THEN 1 ELSE 0 END
            END
        )::numeric(14, 2) AS earned_gross,
        COUNT(*) FILTER (
            WHERE pp.is_sub AND pp.s_day < pr.x_now AND (pp.s_day + pp.dur) > pr.x_now
        )::bigint AS active_obligations
    FROM pp
    CROSS JOIN params pr
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
        'as_of', to_char(p_to, 'YYYY-MM-DD'),
        'received_net', COALESCE((SELECT received_net FROM snap), 0)::text,
        'received_gross', COALESCE((SELECT received_gross FROM snap), 0)::text,
        'earned_net', COALESCE((SELECT earned_net FROM snap), 0)::text,
        'earned_gross', COALESCE((SELECT earned_gross FROM snap), 0)::text,
        'deferred_net', COALESCE((SELECT received_net - earned_net FROM snap), 0)::text,
        'deferred_gross', COALESCE((SELECT received_gross - earned_gross FROM snap), 0)::text,
        'active_obligations', COALESCE((SELECT active_obligations FROM snap), 0)
    )
);
$$;
