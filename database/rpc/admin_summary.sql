-- Сводка админки за календарный период [p_from, p_to] (Europe/Moscow).
CREATE OR REPLACE FUNCTION rpc_admin_summary (p_from date, p_to date)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
WITH msk AS (
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
expiry_renewal_base AS (
    SELECT
        qu.id AS user_id,
        qu.subscription_until AS expiry_day,
        EXISTS (
            SELECT 1
            FROM payments p
            WHERE p.user_id = qu.id
        ) AS had_paid_before,
        EXISTS (
            SELECT 1
            FROM payments p
            WHERE p.user_id = qu.id
              AND (p.created_at AT TIME ZONE 'Europe/Moscow')::date = qu.subscription_until
        ) AS paid_on_expiry,
        EXISTS (
            SELECT 1
            FROM payments p
            WHERE p.user_id = qu.id
              AND (p.created_at AT TIME ZONE 'Europe/Moscow')::date >= qu.subscription_until
              AND (p.created_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN p_from AND p_to
        ) AS returned_in_period
    FROM qualified_users qu
    WHERE qu.subscription_until IS NOT NULL
      AND qu.subscription_until BETWEEN p_from AND p_to
),
renewal_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE had_paid_before)::bigint AS eligible,
        COUNT(*) FILTER (WHERE had_paid_before AND paid_on_expiry)::bigint AS renewed,
        COUNT(*) FILTER (WHERE had_paid_before AND returned_in_period)::bigint AS returned
    FROM expiry_renewal_base
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
    'returned_after_expiry', (SELECT returned FROM renewal_stats)
);
$$;
