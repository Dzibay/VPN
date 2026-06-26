-- Сводка админки за календарный период [p_from, p_to] (Europe/Moscow).
CREATE OR REPLACE FUNCTION rpc_admin_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH RECURSIVE
msk AS (
    SELECT (NOW() AT TIME ZONE 'Europe/Moscow')::date AS today
),
qualified_users AS (
    SELECT
        u.id,
        u.registered_at,
        u.subscription_until
    FROM users u
    WHERE u.telegram_id IS NOT NULL
       OR (
           u.email IS NOT NULL
           AND BTRIM(u.email) <> ''
           AND u.email_verified_at IS NOT NULL
       )
),
paying_user_ids AS (
    SELECT DISTINCT p.user_id
    FROM payments p
    WHERE p.user_id IS NOT NULL
),
users_total AS (
    SELECT COUNT(*)::bigint AS n
    FROM qualified_users
),
users_in_period AS (
    SELECT COUNT(*)::bigint AS n
    FROM qualified_users qu
    WHERE qu.registered_at IS NOT NULL
      AND (qu.registered_at AT TIME ZONE 'Europe/Moscow')::date
          BETWEEN p_from AND p_to
),
active_users AS (
    SELECT COUNT(*)::bigint AS n
    FROM qualified_users qu
    CROSS JOIN msk m
    WHERE qu.subscription_until IS NOT NULL
      AND qu.subscription_until >= m.today
),
expiring AS (
    SELECT
        COUNT(*)::bigint AS total,
        COUNT(*) FILTER (WHERE pu.user_id IS NOT NULL)::bigint AS paid
    FROM qualified_users qu
    CROSS JOIN msk m
    LEFT JOIN paying_user_ids pu ON pu.user_id = qu.id
    WHERE qu.subscription_until IS NOT NULL
      AND qu.subscription_until >= m.today
      AND qu.subscription_until < m.today + 7
),
payments_period AS (
    SELECT
        COALESCE(SUM(s.cnt), 0)::bigint AS cnt,
        COALESCE(SUM(s.gross), 0)::numeric(14, 2) AS revenue
    FROM stats_payments_daily_msk s
    WHERE s.day_msk BETWEEN p_from AND p_to
),
payments_in_period AS (
    SELECT
        p.user_id,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS pay_day
    FROM payments p
    INNER JOIN qualified_users qu ON qu.id = p.user_id
    WHERE p.user_id IS NOT NULL
      AND (p.created_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN p_from AND p_to
),
paying_users_in_period AS (
    SELECT COUNT(DISTINCT pip.user_id)::bigint AS n
    FROM payments_in_period pip
),
payments_for_replay AS (
    SELECT
        p.user_id,
        p.id,
        (p.created_at AT TIME ZONE 'Europe/Moscow')::date AS pay_day,
        GREATEST(COALESCE(NULLIF(p.months, 0), 1), 1) AS months,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id ORDER BY p.created_at ASC, p.id ASC
        )::bigint AS pay_num
    FROM payments p
    INNER JOIN qualified_users qu ON qu.id = p.user_id
    WHERE p.user_id IS NOT NULL
      AND COALESCE(p.months, 0) >= 1
),
payment_chain AS (
    SELECT
        pr.user_id,
        pr.pay_day,
        pr.months,
        pr.pay_num,
        pr.pay_day AS sub_start,
        pr.pay_day + pr.months * 31 AS sub_until_after
    FROM payments_for_replay pr
    WHERE pr.pay_num = 1

    UNION ALL

    SELECT
        pr.user_id,
        pr.pay_day,
        pr.months,
        pr.pay_num,
        CASE
            WHEN pc.sub_until_after >= pr.pay_day THEN pc.sub_until_after
            ELSE pr.pay_day
        END AS sub_start,
        (CASE
            WHEN pc.sub_until_after >= pr.pay_day THEN pc.sub_until_after
            ELSE pr.pay_day
        END) + pr.months * 31 AS sub_until_after
    FROM payments_for_replay pr
    INNER JOIN payment_chain pc
        ON pc.user_id = pr.user_id
       AND pr.pay_num = pc.pay_num + 1
),
expiry_with_next AS (
    SELECT
        pc.user_id,
        pc.sub_until_after AS expiry_day,
        LEAD(pc.pay_day) OVER (
            PARTITION BY pc.user_id ORDER BY pc.pay_num
        ) AS next_pay_day
    FROM payment_chain pc
),
renewal_stats AS (
    SELECT
        COUNT(*)::bigint AS eligible,
        COUNT(*) FILTER (
            WHERE ewn.next_pay_day = ewn.expiry_day
        )::bigint AS renewed,
        COUNT(*) FILTER (
            WHERE ewn.next_pay_day < ewn.expiry_day
        )::bigint AS renewed_early,
        COUNT(*) FILTER (
            WHERE ewn.next_pay_day > ewn.expiry_day
              AND ewn.next_pay_day BETWEEN p_from AND p_to
        )::bigint AS returned
    FROM expiry_with_next ewn
    WHERE ewn.expiry_day BETWEEN p_from AND p_to
),
payments_total AS (
    SELECT COALESCE(SUM(s.gross), 0)::numeric(14, 2) AS revenue
    FROM stats_payments_daily_msk s
),paying_users AS (
    SELECT COUNT(DISTINCT p.user_id)::bigint AS n
    FROM payments p
    INNER JOIN qualified_users qu ON qu.id = p.user_id
    WHERE p.user_id IS NOT NULL
),
avg_per_payer AS (
    SELECT
        CASE
            WHEN pu.n > 0 THEN (pt.revenue / pu.n::numeric)::numeric(14, 2)
            ELSE 0::numeric(14, 2)
        END AS avg_revenue
    FROM paying_users pu
    CROSS JOIN payments_total pt
)
SELECT jsonb_build_object(
    'period_from', p_from,
    'period_to', p_to,
    'msk_today', (SELECT today FROM msk),
    'users_total', (SELECT n FROM users_total),
    'users_in_period', (SELECT n FROM users_in_period),
    'active_users', (SELECT n FROM active_users),
    'expiring_subscriptions', (SELECT total FROM expiring),
    'expiring_paid', (SELECT paid FROM expiring),
    'revenue_period', (SELECT revenue FROM payments_period),
    'payments_count', (SELECT cnt FROM payments_period),
    'revenue_total', (SELECT revenue FROM payments_total),
    'paying_users_total', (SELECT n FROM paying_users),
    'avg_revenue_per_paying_user', (SELECT avg_revenue FROM avg_per_payer),
    'paying_users_in_period', (SELECT n FROM paying_users_in_period),
    'renewal_eligible', (SELECT eligible FROM renewal_stats),
    'renewed_on_expiry', (SELECT renewed FROM renewal_stats),
    'renewed_early', (SELECT renewed_early FROM renewal_stats),
    'returned_after_expiry', (SELECT returned FROM renewal_stats)
);
$$;
