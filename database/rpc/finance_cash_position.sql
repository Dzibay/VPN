-- Сводные суммы для cash position (один round-trip вместо 7 запросов).
DROP FUNCTION IF EXISTS rpc_finance_cash_position(date);

-- Multi-tenant: p_project_id=NULL → агрегат.
CREATE OR REPLACE FUNCTION rpc_finance_cash_position (
    p_as_of date,
    p_project_id bigint DEFAULT NULL
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
SELECT jsonb_build_object(
    'opening',
    COALESCE((
        SELECT SUM(ca.opening_balance)
        FROM cash_accounts ca
        WHERE ca.opened_on <= p_as_of
          AND (p_project_id IS NULL OR ca.project_id = p_project_id)
    ), 0)::text,
    'adjustments',
    COALESCE((
        SELECT SUM(ct.amount)
        FROM cash_transactions ct
        WHERE ct.occurred_on <= p_as_of
          AND (p_project_id IS NULL OR ct.project_id = p_project_id)
    ), 0)::text,
    'company_expenses_paid',
    COALESCE((
        SELECT SUM(e.amount)
        FROM expenses e
        WHERE e.payment_source = 'company'
          AND e.incurred_on <= p_as_of
          AND (p_project_id IS NULL OR e.project_id = p_project_id)
    ), 0)::text,
    'unpaid_expenses',
    COALESCE((
        SELECT SUM(e.amount)
        FROM expenses e
        WHERE e.payment_source = 'unpaid'
          AND e.incurred_on <= p_as_of
          AND (p_project_id IS NULL OR e.project_id = p_project_id)
    ), 0)::text,
    'payables_open',
    COALESCE((
        SELECT SUM(p.amount - p.paid_amount)
        FROM payables p
        WHERE p.status IN ('open', 'partial')
          AND (p_project_id IS NULL OR p.project_id = p_project_id)
    ), 0)::text,
    'payables_paid',
    COALESCE((
        SELECT SUM(p.paid_amount)
        FROM payables p
        WHERE p.status IN ('partial', 'paid')
          AND (p_project_id IS NULL OR p.project_id = p_project_id)
    ), 0)::text,
    'refunds',
    COALESCE((
        SELECT SUM(r.net_amount)
        FROM refunds r
        LEFT JOIN users ru ON ru.id = r.user_id
        LEFT JOIN payments rp ON rp.id = r.payment_id
        WHERE r.status = 'succeeded'
          AND r.refunded_on <= p_as_of
          AND (
              p_project_id IS NULL
              OR COALESCE(ru.project_id, rp.project_id) = p_project_id
          )
    ), 0)::text,
    'withdrawals',
    COALESCE((
        SELECT SUM(pw.amount)
        FROM profit_withdrawals pw
        WHERE pw.status = 'succeeded'
          AND pw.withdrawn_on <= p_as_of
          AND (p_project_id IS NULL OR pw.project_id = p_project_id)
    ), 0)::text
);
$$;
