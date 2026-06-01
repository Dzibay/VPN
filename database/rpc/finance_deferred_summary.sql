-- Признание выручки по дням и баланс неисполненных обязательств («замороженные деньги»).
--
-- Обязательство есть у любого платежа с months > 0 (в т.ч. YooKassa: payment_kind=one_time,
-- но months берётся из тарифа и подписка продлевается). Окно услуги строится как
-- payment_service.extend_subscription_until — платежи user_id по created_at, каждый следующий
-- стартует от max(текущий subscription_until, дата платежа). Разовые (months=0) — сразу.
--
-- Snapshot (as_of = min(p_to, сегодня МСК), за ВСЁ время):
--   received_* — все поступившие платежи; earned_* — признанная выручка (свободно);
--   deferred_* — received − earned (заморожено); earned ≤ received.
DROP FUNCTION IF EXISTS rpc_finance_deferred_summary (date, date);

CREATE OR REPLACE FUNCTION rpc_finance_deferred_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH RECURSIVE
params AS (
    SELECT
        date_trunc('month', p_from::timestamp)::date AS m_from,
        date_trunc('month', p_to::timestamp)::date AS m_to,
        LEAST(
            p_to,
            (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date
        ) AS as_of,
        LEAST(
            p_to,
            (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date
        ) + 1 AS x_now
),
payment_ordered AS (
    SELECT
        p.id,
        p.user_id,
        p.amount AS gross,
        p.net_amount AS net,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS s_day,
        p.created_at,
        (p.months > 0) AS is_sub,
        (p.months * 31) AS dur,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id
            ORDER BY p.created_at, p.id
        ) AS rn
    FROM payments p
    WHERE p.user_id IS NOT NULL
),
stack AS (
    SELECT
        po.id,
        po.user_id,
        po.gross,
        po.net,
        po.s_day,
        po.is_sub,
        po.dur,
        po.rn,
        CASE WHEN po.is_sub THEN po.s_day END AS svc_start,
        CASE WHEN po.is_sub THEN po.s_day + po.dur END AS svc_end,
        CASE WHEN po.is_sub THEN po.s_day + po.dur END AS sub_until
    FROM payment_ordered po
    WHERE po.rn = 1

    UNION ALL

    SELECT
        po.id,
        po.user_id,
        po.gross,
        po.net,
        po.s_day,
        po.is_sub,
        po.dur,
        po.rn,
        CASE
            WHEN NOT po.is_sub THEN NULL::date
            WHEN s.sub_until IS NOT NULL AND s.sub_until >= po.s_day THEN s.sub_until
            ELSE po.s_day
        END,
        CASE
            WHEN NOT po.is_sub THEN NULL::date
            WHEN s.sub_until IS NOT NULL AND s.sub_until >= po.s_day THEN s.sub_until + po.dur
            ELSE po.s_day + po.dur
        END,
        CASE
            WHEN NOT po.is_sub THEN s.sub_until
            WHEN s.sub_until IS NOT NULL AND s.sub_until >= po.s_day THEN s.sub_until + po.dur
            ELSE po.s_day + po.dur
        END
    FROM payment_ordered po
    INNER JOIN stack s ON s.user_id = po.user_id AND po.rn = s.rn + 1
),
pp_stacked AS (
    SELECT id, user_id, gross, net, s_day, is_sub, dur, svc_start, svc_end
    FROM stack
),
pp_orphan AS (
    -- Платежи без user_id: окно от даты платежа без стека.
    SELECT
        p.id,
        p.user_id,
        p.amount AS gross,
        p.net_amount AS net,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS s_day,
        (p.months > 0) AS is_sub,
        (p.months * 31) AS dur,
        CASE WHEN p.months > 0
            THEN (p.created_at AT TIME ZONE 'Europe/Moscow')::date
        END AS svc_start,
        CASE WHEN p.months > 0
            THEN (p.created_at AT TIME ZONE 'Europe/Moscow')::date + (p.months * 31)
        END AS svc_end
    FROM payments p
    WHERE p.user_id IS NULL
),
pp AS (
    SELECT * FROM pp_stacked
    UNION ALL
    SELECT * FROM pp_orphan
),
earn_frac AS (
    SELECT
        pp.*,
        pr.x_now,
        CASE
            WHEN NOT pp.is_sub
                THEN CASE WHEN pp.s_day < pr.x_now THEN 1::numeric ELSE 0::numeric END
            WHEN pp.svc_start IS NULL
                THEN 0::numeric
            ELSE LEAST(
                GREATEST((pr.x_now - pp.svc_start), 0),
                pp.dur
            )::numeric / pp.dur
        END AS frac_now
    FROM pp
    CROSS JOIN params pr
),
m AS (
    SELECT
        gs::date AS m_start,
        (gs + interval '1 month')::date AS m_next,
        LEAST((gs + interval '1 month')::date, (SELECT x_now FROM params)) AS xe
    FROM generate_series(
        (SELECT m_from FROM params)::timestamp,
        (SELECT m_to FROM params)::timestamp,
        interval '1 month'
    ) AS gs
),
base AS (
    SELECT
        m.m_start,
        pp.net,
        pp.gross,
        CASE
            WHEN NOT pp.is_sub
                THEN CASE WHEN pp.s_day < m.xe THEN 1::numeric ELSE 0::numeric END
            ELSE LEAST(GREATEST((m.xe - pp.svc_start), 0), pp.dur)::numeric / pp.dur
        END AS fe,
        CASE
            WHEN NOT pp.is_sub
                THEN CASE WHEN pp.s_day < m.m_start THEN 1::numeric ELSE 0::numeric END
            ELSE LEAST(GREATEST((m.m_start - pp.svc_start), 0), pp.dur)::numeric / pp.dur
        END AS fs
    FROM m
    INNER JOIN pp ON (
        (pp.is_sub AND pp.svc_start < m.xe AND pp.svc_end > m.m_start)
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
snap_raw AS (
    SELECT
        SUM(CASE WHEN ef.s_day < ef.x_now THEN ef.net ELSE 0 END)::numeric(14, 2) AS received_net,
        SUM(CASE WHEN ef.s_day < ef.x_now THEN ef.gross ELSE 0 END)::numeric(14, 2) AS received_gross,
        SUM(ef.net * ef.frac_now)::numeric(14, 2) AS earned_net_raw,
        SUM(ef.gross * ef.frac_now)::numeric(14, 2) AS earned_gross_raw
    FROM earn_frac ef
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
    )
);
$$;
