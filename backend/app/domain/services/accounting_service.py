"""Бухгалтерия (P&L): налоговые настройки, сводка по месяцам, CRUD расходов/шаблонов/категорий."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_subject import get_request_subject
from app.core.time import utc_now
from app.domain.models.accounting import (
    CashAccountCreateBody,
    CashAccountItem,
    CashAccountPatchBody,
    CashTransactionCreateBody,
    CashTransactionItem,
    ExpenseCategoryCreateBody,
    ExpenseCategoryItem,
    ExpenseCategoryPatchBody,
    ExpenseCreateBody,
    ExpenseItem,
    ExpensePatchBody,
    FinanceAccountingSummaryResponse,
    FinanceCashPosition,
    FinanceCategoryTotal,
    FinanceDeferredSnapshot,
    FinanceUnlockSchedule,
    FinanceSeries,
    FinanceSettings,
    FinanceSettingsPatch,
    FinanceTaxInfo,
    FinanceTotals,
    PayableCreateBody,
    PayableItem,
    PayablePatchBody,
    PayablePaymentBody,
    ProfitWithdrawalCreateBody,
    ProfitWithdrawalItem,
    ProfitWithdrawalPatchBody,
    RecurringExpenseCreateBody,
    RecurringExpenseItem,
    RecurringExpensePatchBody,
    RefundCreateBody,
    RefundItem,
    RefundPatchBody,
)
from app.infrastructure.persistence.models.app_setting import AppSetting
from app.infrastructure.persistence.models.expense import Expense
from app.infrastructure.persistence.models.expense_category import ExpenseCategory
from app.infrastructure.persistence.models.finance import (
    CashAccount,
    CashTransaction,
    Payable,
    ProfitWithdrawal,
    Refund,
)
from app.infrastructure.persistence.models.recurring_expense import RecurringExpense

_FINANCE_SETTINGS_KEY = "finance"


# --------------------------------------------------------------------------- #
# Хелперы
# --------------------------------------------------------------------------- #
def _to_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _money_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _current_user_id() -> int | None:
    uid, _ = get_request_subject()
    return uid


# --------------------------------------------------------------------------- #
# Налоговые настройки
# --------------------------------------------------------------------------- #
def _settings_from_value(value: object) -> FinanceSettings:
    if not isinstance(value, dict):
        return FinanceSettings()
    data = dict(value)
    if "tax_rate" in data and data["tax_rate"] is not None:
        data["tax_rate"] = _to_decimal(data["tax_rate"])
    try:
        return FinanceSettings.model_validate(data)
    except Exception:
        return FinanceSettings()


def _settings_to_jsonable(s: FinanceSettings) -> dict[str, object]:
    return {
        "tax_mode": s.tax_mode,
        "tax_rate": float(s.tax_rate),
        "tax_base": s.tax_base,
        "currency": s.currency,
    }


async def get_finance_settings(session: AsyncSession) -> FinanceSettings:
    row = await session.get(AppSetting, _FINANCE_SETTINGS_KEY)
    if row is None:
        return FinanceSettings()
    return _settings_from_value(row.value)


async def update_finance_settings(
    session: AsyncSession,
    patch: FinanceSettingsPatch,
) -> FinanceSettings:
    row = await session.get(AppSetting, _FINANCE_SETTINGS_KEY)
    current = _settings_from_value(row.value) if row is not None else FinanceSettings()

    data = current.model_dump()
    data.update(patch.model_dump(exclude_unset=True))
    merged = FinanceSettings.model_validate(data)
    payload = _settings_to_jsonable(merged)

    if row is None:
        row = AppSetting(key=_FINANCE_SETTINGS_KEY, value=payload, updated_by=_current_user_id())
        session.add(row)
    else:
        row.value = payload
        row.updated_by = _current_user_id()
        row.updated_at = utc_now()
    await session.flush()
    return merged


# --------------------------------------------------------------------------- #
# Сводка (P&L)
# --------------------------------------------------------------------------- #
def _decimal_list(raw: object, length: int) -> list[Decimal]:
    items = raw if isinstance(raw, list) else []
    out = [_to_decimal(v) for v in items]
    if len(out) < length:
        out.extend(Decimal(0) for _ in range(length - len(out)))
    return out[:length]


async def get_accounting_summary(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
) -> FinanceAccountingSummaryResponse:
    settings = await get_finance_settings(session)

    stmt = text("SELECT rpc_finance_accounting_summary(:p_from, :p_to) AS payload")
    row = (await session.execute(stmt, {"p_from": date_from, "p_to": date_to})).one()
    raw = row.payload if isinstance(row.payload, dict) else {}

    def_stmt = text("SELECT rpc_finance_deferred_summary(:p_from, :p_to) AS payload")
    def_row = (await session.execute(def_stmt, {"p_from": date_from, "p_to": date_to})).one()
    def_raw = def_row.payload if isinstance(def_row.payload, dict) else {}

    months = [str(m) for m in (raw.get("months") or [])]
    n = len(months)

    gross = _decimal_list(raw.get("revenue_gross"), n)
    net = _decimal_list(raw.get("revenue_net"), n)
    commission = _decimal_list(raw.get("psp_commission"), n)
    gross_sub = _decimal_list(raw.get("revenue_gross_subscription"), n)
    gross_one = _decimal_list(raw.get("revenue_gross_one_time"), n)
    expenses = _decimal_list(raw.get("expenses_total"), n)

    refund_stmt = text(
        """
        WITH months AS (
            SELECT gs::date AS m_start
            FROM generate_series(
                date_trunc('month', CAST(:p_from AS date))::timestamp,
                date_trunc('month', CAST(:p_to AS date))::timestamp,
                interval '1 month'
            ) AS gs
        ),
        refunds_by_month AS (
            SELECT
                date_trunc('month', r.refunded_on)::date AS m_start,
                SUM(r.amount)::numeric(14, 2) AS gross,
                SUM(r.net_amount)::numeric(14, 2) AS net
            FROM refunds r
            WHERE r.status = 'succeeded'
              AND date_trunc('month', r.refunded_on)::date
                  BETWEEN date_trunc('month', CAST(:p_from AS date))::date
                      AND date_trunc('month', CAST(:p_to AS date))::date
            GROUP BY 1
        )
        SELECT jsonb_build_object(
            'gross', COALESCE((
                SELECT jsonb_agg(COALESCE(r.gross, 0)::text ORDER BY m.m_start)
                FROM months m LEFT JOIN refunds_by_month r ON r.m_start = m.m_start
            ), '[]'::jsonb),
            'net', COALESCE((
                SELECT jsonb_agg(COALESCE(r.net, 0)::text ORDER BY m.m_start)
                FROM months m LEFT JOIN refunds_by_month r ON r.m_start = m.m_start
            ), '[]'::jsonb)
        ) AS payload
        """
    )
    refund_row = (await session.execute(refund_stmt, {"p_from": date_from, "p_to": date_to})).one()
    refund_raw = refund_row.payload if isinstance(refund_row.payload, dict) else {}
    refunds_gross = _decimal_list(refund_raw.get("gross"), n)
    refunds_net = _decimal_list(refund_raw.get("net"), n)

    earned_net = _decimal_list(def_raw.get("earned_net"), n)
    earned_gross = _decimal_list(def_raw.get("earned_gross"), n)
    deferred_net_end = _decimal_list(def_raw.get("deferred_net_end"), n)
    deferred_gross_end = _decimal_list(def_raw.get("deferred_gross_end"), n)

    rate = settings.tax_rate
    tax_zero = settings.tax_mode == "none" or rate == 0

    tax: list[Decimal] = []
    profit: list[Decimal] = []
    for i in range(n):
        net_after_refunds = net[i] - refunds_net[i]
        gross_after_refunds = gross[i] - refunds_gross[i]
        if tax_zero:
            base = Decimal(0)
        elif settings.tax_base == "gross":
            base = gross_after_refunds
        elif settings.tax_base == "net":
            base = net_after_refunds
        else:  # profit
            base = max(Decimal(0), net_after_refunds - expenses[i])
        t = (base * rate) if not tax_zero else Decimal(0)
        if t < 0:
            t = Decimal(0)
        tax.append(t)
        profit.append(net_after_refunds - expenses[i] - t)

    # Итоги
    total_gross = sum(gross, Decimal(0))
    total_net = sum(net, Decimal(0))
    total_refunds = sum(refunds_net, Decimal(0))
    total_net_after_refunds = total_net - total_refunds
    total_commission = sum(commission, Decimal(0))
    total_expenses = sum(expenses, Decimal(0))
    total_tax = sum(tax, Decimal(0))
    total_profit = sum(profit, Decimal(0))
    margin = (total_profit / total_gross * Decimal(100)) if total_gross > 0 else Decimal(0)

    # Расходы по категориям
    ebc_raw = raw.get("expenses_by_category")
    ebc: dict[str, list[str]] = {}
    if isinstance(ebc_raw, dict):
        for slug, arr in ebc_raw.items():
            ebc[str(slug)] = [_money_str(v) for v in _decimal_list(arr, n)]

    cat_meta = await _categories_meta_by_slug(session)
    category_totals: list[FinanceCategoryTotal] = []
    for slug, arr in ebc.items():
        total_cat = sum((_to_decimal(v) for v in arr), Decimal(0))
        if total_cat <= 0:
            continue
        title, color = cat_meta.get(slug, (slug, "#94a3b8"))
        category_totals.append(
            FinanceCategoryTotal(slug=slug, title=title, color=color, total=_money_str(total_cat))
        )
    category_totals.sort(key=lambda c: _to_decimal(c.total), reverse=True)

    payment_count = int(_to_decimal(raw.get("payment_count")))

    series = FinanceSeries(
        revenue_gross=[_money_str(v) for v in gross],
        revenue_net=[_money_str(v) for v in net],
        psp_commission=[_money_str(v) for v in commission],
        revenue_gross_subscription=[_money_str(v) for v in gross_sub],
        revenue_gross_one_time=[_money_str(v) for v in gross_one],
        expenses_total=[_money_str(v) for v in expenses],
        tax=[_money_str(v) for v in tax],
        profit_net=[_money_str(v) for v in profit],
        earned_net=[_money_str(v) for v in earned_net],
        earned_gross=[_money_str(v) for v in earned_gross],
        deferred_net_end=[_money_str(v) for v in deferred_net_end],
        deferred_gross_end=[_money_str(v) for v in deferred_gross_end],
    )

    snap = def_raw.get("snapshot") if isinstance(def_raw.get("snapshot"), dict) else {}
    deferred = FinanceDeferredSnapshot(
        as_of=snap.get("as_of") or date_to,
        received_net=_money_str(_to_decimal(snap.get("received_net"))),
        received_gross=_money_str(_to_decimal(snap.get("received_gross"))),
        earned_net=_money_str(_to_decimal(snap.get("earned_net"))),
        earned_gross=_money_str(_to_decimal(snap.get("earned_gross"))),
        deferred_net=_money_str(_to_decimal(snap.get("deferred_net"))),
        deferred_gross=_money_str(_to_decimal(snap.get("deferred_gross"))),
        active_obligations=int(_to_decimal(snap.get("active_obligations"))),
    )

    unlock_raw = def_raw.get("unlock") if isinstance(def_raw.get("unlock"), dict) else {}
    unlock_days = [str(d) for d in (unlock_raw.get("days") or [])]
    unlock_months = [str(m) for m in (unlock_raw.get("months") or [])]
    unlock = FinanceUnlockSchedule(
        days=unlock_days,
        amounts_net=[_money_str(_to_decimal(v)) for v in (unlock_raw.get("amounts_net") or [])],
        months=unlock_months,
        amounts_net_monthly=[
            _money_str(_to_decimal(v)) for v in (unlock_raw.get("amounts_net_monthly") or [])
        ],
    )

    period_withdrawn = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(ProfitWithdrawal.amount), 0)).where(
            ProfitWithdrawal.status == "succeeded",
            ProfitWithdrawal.withdrawn_on >= date_from,
            ProfitWithdrawal.withdrawn_on <= date_to,
        ),
    )
    cash_position = await _build_cash_position(
        session,
        as_of=date_to,
        deferred=deferred,
        tax_reserved=total_tax,
    )

    return FinanceAccountingSummaryResponse(
        range_from=date_from,
        range_to=date_to,
        currency=settings.currency,
        months=months,
        series=series,
        expenses_by_category=ebc,
        category_totals=category_totals,
        totals=FinanceTotals(
            revenue_gross=_money_str(total_gross),
            revenue_net=_money_str(total_net),
            psp_commission=_money_str(total_commission),
            refunds_total=_money_str(total_refunds),
            revenue_net_after_refunds=_money_str(total_net_after_refunds),
            expenses_total=_money_str(total_expenses),
            tax=_money_str(total_tax),
            profit_net=_money_str(total_profit),
            profit_withdrawn=_money_str(period_withdrawn),
            margin_percent=str(margin.quantize(Decimal("0.1"))),
            payment_count=payment_count,
        ),
        tax=FinanceTaxInfo(mode=settings.tax_mode, rate=str(rate), base=settings.tax_base),
        deferred=deferred,
        cash_position=cash_position,
        unlock=unlock,
    )


async def _sum_decimal(session: AsyncSession, stmt) -> Decimal:
    return _to_decimal(await session.scalar(stmt))


async def _build_cash_position(
    session: AsyncSession,
    *,
    as_of: date,
    deferred: FinanceDeferredSnapshot,
    tax_reserved: Decimal,
) -> FinanceCashPosition:
    opening = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(CashAccount.opening_balance), 0)).where(
            CashAccount.opened_on <= as_of
        ),
    )
    adjustments = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(CashTransaction.amount), 0)).where(
            CashTransaction.occurred_on <= as_of
        ),
    )
    company_expenses_paid = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.payment_source == "company",
            Expense.incurred_on <= as_of,
        ),
    )
    unpaid_expenses = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.payment_source == "unpaid",
            Expense.incurred_on <= as_of,
        ),
    )
    payables_open = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(Payable.amount - Payable.paid_amount), 0)).where(
            Payable.status.in_(("open", "partial"))
        ),
    )
    payables_paid = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(Payable.paid_amount), 0)).where(
            Payable.status.in_(("partial", "paid"))
        ),
    )
    refunds = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(Refund.net_amount), 0)).where(
            Refund.status == "succeeded",
            Refund.refunded_on <= as_of,
        ),
    )
    withdrawals = await _sum_decimal(
        session,
        select(func.coalesce(func.sum(ProfitWithdrawal.amount), 0)).where(
            ProfitWithdrawal.status == "succeeded",
            ProfitWithdrawal.withdrawn_on <= as_of,
        ),
    )

    received = _to_decimal(deferred.received_net)
    earned = _to_decimal(deferred.earned_net)
    frozen = _to_decimal(deferred.deferred_net)
    cash_balance = (
        opening
        + received
        + adjustments
        - company_expenses_paid
        - payables_paid
        - refunds
        - withdrawals
    )
    reserve_total = frozen + payables_open + unpaid_expenses + tax_reserved
    withdrawable = cash_balance - reserve_total
    if withdrawable < 0:
        withdrawable = Decimal(0)

    return FinanceCashPosition(
        as_of=as_of,
        cash_balance=_money_str(cash_balance),
        cash_accounts_total=_money_str(opening),
        cash_adjustments=_money_str(adjustments),
        received_net=_money_str(received),
        earned_net=_money_str(earned),
        deferred_net=_money_str(frozen),
        payables_open=_money_str(payables_open),
        unpaid_expenses=_money_str(unpaid_expenses),
        refunds_succeeded=_money_str(refunds),
        profit_withdrawn=_money_str(withdrawals),
        tax_reserved=_money_str(tax_reserved),
        reserve_total=_money_str(reserve_total),
        withdrawable_profit=_money_str(withdrawable),
    )


# --------------------------------------------------------------------------- #
# Категории
# --------------------------------------------------------------------------- #
async def _categories_meta_by_slug(session: AsyncSession) -> dict[str, tuple[str, str]]:
    rows = (await session.scalars(select(ExpenseCategory))).all()
    return {str(r.slug): (str(r.title), str(r.color)) for r in rows}


async def list_categories(
    session: AsyncSession,
    *,
    include_archived: bool = True,
) -> list[ExpenseCategoryItem]:
    stmt = select(ExpenseCategory)
    if not include_archived:
        stmt = stmt.where(ExpenseCategory.archived.is_(False))
    stmt = stmt.order_by(ExpenseCategory.sort_order.asc(), ExpenseCategory.id.asc())
    rows = (await session.scalars(stmt)).all()
    return [ExpenseCategoryItem.model_validate(r) for r in rows]


async def create_category(
    session: AsyncSession,
    body: ExpenseCategoryCreateBody,
) -> ExpenseCategoryItem:
    exists = await session.scalar(
        select(ExpenseCategory.id).where(ExpenseCategory.slug == body.slug)
    )
    if exists is not None:
        raise LookupError("slug_taken")
    row = ExpenseCategory(
        slug=body.slug,
        title=body.title.strip(),
        color=body.color,
        sort_order=body.sort_order,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return ExpenseCategoryItem.model_validate(row)


async def update_category(
    session: AsyncSession,
    category_id: int,
    patch: ExpenseCategoryPatchBody,
) -> ExpenseCategoryItem:
    row = await session.get(ExpenseCategory, category_id)
    if row is None:
        raise LookupError("category_not_found")
    data = patch.model_dump(exclude_unset=True)
    if "title" in data:
        row.title = str(data["title"]).strip()
    if "color" in data:
        row.color = data["color"]
    if "sort_order" in data:
        row.sort_order = data["sort_order"]
    if "archived" in data:
        row.archived = bool(data["archived"])
    await session.flush()
    await session.refresh(row)
    return ExpenseCategoryItem.model_validate(row)


async def delete_category(session: AsyncSession, category_id: int) -> None:
    row = await session.get(ExpenseCategory, category_id)
    if row is None:
        raise LookupError("category_not_found")
    await session.delete(row)
    await session.flush()


# --------------------------------------------------------------------------- #
# Разовые расходы
# --------------------------------------------------------------------------- #
async def list_expenses(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[ExpenseItem], int]:
    conds = []
    if date_from is not None:
        conds.append(Expense.incurred_on >= date_from)
    if date_to is not None:
        conds.append(Expense.incurred_on <= date_to)

    count_stmt = select(func.count()).select_from(Expense)
    list_stmt = select(Expense)
    if conds:
        count_stmt = count_stmt.where(*conds)
        list_stmt = list_stmt.where(*conds)

    total = int(await session.scalar(count_stmt) or 0)
    list_stmt = (
        list_stmt.order_by(Expense.incurred_on.desc(), Expense.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.scalars(list_stmt)).all())
    return [ExpenseItem.model_validate(r) for r in rows], total


async def create_expense(session: AsyncSession, body: ExpenseCreateBody) -> ExpenseItem:
    await _ensure_category_exists(session, body.category_id)
    await _ensure_cash_account_exists(session, body.cash_account_id)
    paid_by = (body.paid_by_name or "").strip() or None
    if body.payment_source == "person" and not paid_by:
        raise ValueError("paid_by_name_required")
    row = Expense(
        incurred_on=body.incurred_on,
        amount=body.amount,
        category_id=body.category_id,
        title=body.title.strip(),
        note=(body.note or None),
        payment_source=body.payment_source,
        paid_by_name=paid_by,
        cash_account_id=body.cash_account_id if body.payment_source == "company" else None,
        paid_on=body.paid_on if body.payment_source == "company" else None,
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    if body.payment_source == "person":
        session.add(
            Payable(
                counterparty_name=paid_by or "Сотрудник",
                title=row.title,
                amount=row.amount,
                source_type="expense",
                expense_id=row.id,
                incurred_on=row.incurred_on,
                note=row.note,
                created_by=_current_user_id(),
            )
        )
        await session.flush()
    await session.refresh(row)
    return ExpenseItem.model_validate(row)


async def update_expense(
    session: AsyncSession,
    expense_id: int,
    patch: ExpensePatchBody,
) -> ExpenseItem:
    row = await session.get(Expense, expense_id)
    if row is None:
        raise LookupError("expense_not_found")
    data = patch.model_dump(exclude_unset=True)
    if "category_id" in data:
        await _ensure_category_exists(session, data["category_id"])
        row.category_id = data["category_id"]
    if "incurred_on" in data:
        row.incurred_on = data["incurred_on"]
    if "amount" in data:
        row.amount = data["amount"]
    if "title" in data:
        row.title = str(data["title"]).strip()
    if "note" in data:
        row.note = data["note"] or None
    if "payment_source" in data:
        row.payment_source = data["payment_source"]
    if "paid_by_name" in data:
        row.paid_by_name = (data["paid_by_name"] or "").strip() or None
    if "cash_account_id" in data:
        await _ensure_cash_account_exists(session, data["cash_account_id"])
        row.cash_account_id = data["cash_account_id"]
    if "paid_on" in data:
        row.paid_on = data["paid_on"]
    if row.payment_source == "person" and not row.paid_by_name:
        raise ValueError("paid_by_name_required")
    if row.payment_source != "company":
        row.cash_account_id = None
        row.paid_on = None
    existing_payable = await session.scalar(
        select(Payable).where(Payable.source_type == "expense", Payable.expense_id == row.id)
    )
    if row.payment_source == "person":
        if existing_payable is None:
            session.add(
                Payable(
                    counterparty_name=row.paid_by_name or "Сотрудник",
                    title=row.title,
                    amount=row.amount,
                    source_type="expense",
                    expense_id=row.id,
                    incurred_on=row.incurred_on,
                    note=row.note,
                    created_by=_current_user_id(),
                )
            )
        elif existing_payable.status != "paid":
            existing_payable.counterparty_name = row.paid_by_name or existing_payable.counterparty_name
            existing_payable.title = row.title
            existing_payable.amount = row.amount
            existing_payable.incurred_on = row.incurred_on
            existing_payable.note = row.note
            existing_payable.status = _payable_status(existing_payable.amount, existing_payable.paid_amount)
    elif existing_payable is not None and existing_payable.status != "paid":
        existing_payable.status = "cancelled"
    await session.flush()
    await session.refresh(row)
    return ExpenseItem.model_validate(row)


async def delete_expenses_by_ids(session: AsyncSession, *, ids: list[int]) -> int:
    uniq_ids = sorted({int(v) for v in ids if int(v) > 0})
    if not uniq_ids:
        return 0
    res = await session.execute(delete(Expense).where(Expense.id.in_(uniq_ids)))
    return int(res.rowcount or 0)


# --------------------------------------------------------------------------- #
# Повторяющиеся расходы (шаблоны)
# --------------------------------------------------------------------------- #
async def list_recurring_expenses(session: AsyncSession) -> list[RecurringExpenseItem]:
    stmt = select(RecurringExpense).order_by(
        RecurringExpense.active.desc(), RecurringExpense.id.desc()
    )
    rows = (await session.scalars(stmt)).all()
    return [RecurringExpenseItem.model_validate(r) for r in rows]


async def create_recurring_expense(
    session: AsyncSession,
    body: RecurringExpenseCreateBody,
) -> RecurringExpenseItem:
    await _ensure_category_exists(session, body.category_id)
    row = RecurringExpense(
        title=body.title.strip(),
        amount=body.amount,
        category_id=body.category_id,
        note=(body.note or None),
        day_of_month=body.day_of_month,
        start_month=body.start_month,
        end_month=body.end_month,
        active=body.active,
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return RecurringExpenseItem.model_validate(row)


async def update_recurring_expense(
    session: AsyncSession,
    recurring_id: int,
    patch: RecurringExpensePatchBody,
) -> RecurringExpenseItem:
    row = await session.get(RecurringExpense, recurring_id)
    if row is None:
        raise LookupError("recurring_not_found")
    data = patch.model_dump(exclude_unset=True)
    if "category_id" in data:
        await _ensure_category_exists(session, data["category_id"])
        row.category_id = data["category_id"]
    if "title" in data:
        row.title = str(data["title"]).strip()
    if "amount" in data:
        row.amount = data["amount"]
    if "note" in data:
        row.note = data["note"] or None
    if "day_of_month" in data:
        row.day_of_month = data["day_of_month"]
    if "start_month" in data:
        row.start_month = data["start_month"]
    if "end_month" in data:
        row.end_month = data["end_month"]
    if "active" in data:
        row.active = bool(data["active"])

    if row.end_month is not None and row.end_month < row.start_month:
        raise ValueError("end_month_before_start_month")

    await session.flush()
    await session.refresh(row)
    return RecurringExpenseItem.model_validate(row)


async def delete_recurring_expense(session: AsyncSession, recurring_id: int) -> None:
    row = await session.get(RecurringExpense, recurring_id)
    if row is None:
        raise LookupError("recurring_not_found")
    await session.delete(row)
    await session.flush()


async def _ensure_category_exists(session: AsyncSession, category_id: int | None) -> None:
    if category_id is None:
        return
    if await session.get(ExpenseCategory, category_id) is None:
        raise LookupError("category_not_found")


async def _ensure_cash_account_exists(session: AsyncSession, account_id: int | None) -> None:
    if account_id is None:
        return
    if await session.get(CashAccount, account_id) is None:
        raise LookupError("cash_account_not_found")


# --------------------------------------------------------------------------- #
# Счета и ручные кассовые корректировки
# --------------------------------------------------------------------------- #
async def list_cash_accounts(session: AsyncSession) -> list[CashAccountItem]:
    rows = (
        await session.scalars(
            select(CashAccount).order_by(CashAccount.active.desc(), CashAccount.id.asc())
        )
    ).all()
    return [CashAccountItem.model_validate(r) for r in rows]


async def create_cash_account(session: AsyncSession, body: CashAccountCreateBody) -> CashAccountItem:
    row = CashAccount(
        name=body.name.strip(),
        kind=body.kind,
        currency=body.currency.strip() or "RUB",
        opening_balance=body.opening_balance,
        opened_on=body.opened_on,
        active=body.active,
        is_default=body.is_default,
        created_by=_current_user_id(),
    )
    if body.is_default:
        await session.execute(
            text("UPDATE cash_accounts SET is_default = FALSE WHERE is_default = TRUE")
        )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return CashAccountItem.model_validate(row)


async def update_cash_account(
    session: AsyncSession,
    account_id: int,
    patch: CashAccountPatchBody,
) -> CashAccountItem:
    row = await session.get(CashAccount, account_id)
    if row is None:
        raise LookupError("cash_account_not_found")
    data = patch.model_dump(exclude_unset=True)
    if data.get("is_default") is True:
        await session.execute(
            text("UPDATE cash_accounts SET is_default = FALSE WHERE is_default = TRUE AND id <> :id"),
            {"id": account_id},
        )
    for key, value in data.items():
        if key == "name":
            value = str(value).strip()
        if key == "currency":
            value = str(value).strip() or "RUB"
        setattr(row, key, value)
    await session.flush()
    await session.refresh(row)
    return CashAccountItem.model_validate(row)


async def list_cash_transactions(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[CashTransactionItem], int]:
    total = int(await session.scalar(select(func.count()).select_from(CashTransaction)) or 0)
    rows = (
        await session.scalars(
            select(CashTransaction)
            .order_by(CashTransaction.occurred_on.desc(), CashTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [CashTransactionItem.model_validate(r) for r in rows], total


async def create_cash_transaction(
    session: AsyncSession,
    body: CashTransactionCreateBody,
) -> CashTransactionItem:
    await _ensure_cash_account_exists(session, body.account_id)
    row = CashTransaction(
        account_id=body.account_id,
        occurred_on=body.occurred_on,
        amount=body.amount,
        kind=body.kind,
        title=body.title.strip(),
        note=(body.note or None),
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return CashTransactionItem.model_validate(row)


# --------------------------------------------------------------------------- #
# Долги, возвраты, вывод прибыли
# --------------------------------------------------------------------------- #
async def list_payables(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status_filter: str | None = None,
) -> tuple[list[PayableItem], int]:
    conds = []
    if status_filter:
        conds.append(Payable.status == status_filter)
    count_stmt = select(func.count()).select_from(Payable)
    list_stmt = select(Payable)
    if conds:
        count_stmt = count_stmt.where(*conds)
        list_stmt = list_stmt.where(*conds)
    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        await session.scalars(
            list_stmt.order_by(Payable.status.asc(), Payable.incurred_on.desc(), Payable.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [PayableItem.model_validate(r) for r in rows], total


async def create_payable(session: AsyncSession, body: PayableCreateBody) -> PayableItem:
    row = Payable(
        counterparty_name=body.counterparty_name.strip(),
        title=body.title.strip(),
        amount=body.amount,
        source_type=body.source_type,
        expense_id=body.expense_id,
        incurred_on=body.incurred_on,
        due_on=body.due_on,
        note=(body.note or None),
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return PayableItem.model_validate(row)


def _payable_status(amount: Decimal, paid: Decimal) -> str:
    if paid <= 0:
        return "open"
    if paid >= amount:
        return "paid"
    return "partial"


async def update_payable(
    session: AsyncSession,
    payable_id: int,
    patch: PayablePatchBody,
) -> PayableItem:
    row = await session.get(Payable, payable_id)
    if row is None:
        raise LookupError("payable_not_found")
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key in {"counterparty_name", "title"}:
            value = str(value).strip()
        if key == "note":
            value = value or None
        setattr(row, key, value)
    if row.status != "cancelled":
        row.status = _payable_status(row.amount, row.paid_amount)
    await session.flush()
    await session.refresh(row)
    return PayableItem.model_validate(row)


async def pay_payable(
    session: AsyncSession,
    payable_id: int,
    body: PayablePaymentBody,
) -> PayableItem:
    row = await session.get(Payable, payable_id)
    if row is None:
        raise LookupError("payable_not_found")
    if row.status == "cancelled":
        raise ValueError("payable_cancelled")
    await _ensure_cash_account_exists(session, body.account_id)
    new_paid = row.paid_amount + body.amount
    if new_paid > row.amount:
        raise ValueError("payable_overpaid")
    row.paid_amount = new_paid
    row.status = _payable_status(row.amount, row.paid_amount)
    await session.flush()
    await session.refresh(row)
    return PayableItem.model_validate(row)


async def list_refunds(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[RefundItem], int]:
    total = int(await session.scalar(select(func.count()).select_from(Refund)) or 0)
    rows = (
        await session.scalars(
            select(Refund)
            .order_by(Refund.refunded_on.desc(), Refund.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [RefundItem.model_validate(r) for r in rows], total


async def create_refund(session: AsyncSession, body: RefundCreateBody) -> RefundItem:
    await _ensure_cash_account_exists(session, body.account_id)
    row = Refund(
        payment_id=body.payment_id,
        user_id=body.user_id,
        account_id=body.account_id,
        refunded_on=body.refunded_on,
        amount=body.amount,
        net_amount=body.net_amount or body.amount,
        status=body.status,
        reason=(body.reason or None),
        note=(body.note or None),
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return RefundItem.model_validate(row)


async def update_refund(
    session: AsyncSession,
    refund_id: int,
    patch: RefundPatchBody,
) -> RefundItem:
    row = await session.get(Refund, refund_id)
    if row is None:
        raise LookupError("refund_not_found")
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value or None if key in {"reason", "note"} else value)
    await session.flush()
    await session.refresh(row)
    return RefundItem.model_validate(row)


async def list_profit_withdrawals(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[ProfitWithdrawalItem], int]:
    total = int(await session.scalar(select(func.count()).select_from(ProfitWithdrawal)) or 0)
    rows = (
        await session.scalars(
            select(ProfitWithdrawal)
            .order_by(ProfitWithdrawal.withdrawn_on.desc(), ProfitWithdrawal.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [ProfitWithdrawalItem.model_validate(r) for r in rows], total


async def create_profit_withdrawal(
    session: AsyncSession,
    body: ProfitWithdrawalCreateBody,
) -> ProfitWithdrawalItem:
    await _ensure_cash_account_exists(session, body.account_id)
    row = ProfitWithdrawal(
        account_id=body.account_id,
        withdrawn_on=body.withdrawn_on,
        amount=body.amount,
        recipient_name=body.recipient_name.strip(),
        status=body.status,
        note=(body.note or None),
        created_by=_current_user_id(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return ProfitWithdrawalItem.model_validate(row)


async def update_profit_withdrawal(
    session: AsyncSession,
    withdrawal_id: int,
    patch: ProfitWithdrawalPatchBody,
) -> ProfitWithdrawalItem:
    row = await session.get(ProfitWithdrawal, withdrawal_id)
    if row is None:
        raise LookupError("withdrawal_not_found")
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value or None if key == "note" else value)
    await session.flush()
    await session.refresh(row)
    return ProfitWithdrawalItem.model_validate(row)
