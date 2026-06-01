"""Бухгалтерия (P&L): налоговые настройки, сводка по месяцам, CRUD расходов/шаблонов/категорий."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_subject import get_request_subject
from app.core.time import utc_now
from app.domain.models.accounting import (
    ExpenseCategoryCreateBody,
    ExpenseCategoryItem,
    ExpenseCategoryPatchBody,
    ExpenseCreateBody,
    ExpenseItem,
    ExpensePatchBody,
    FinanceAccountingSummaryResponse,
    FinanceCategoryTotal,
    FinanceSeries,
    FinanceSettings,
    FinanceSettingsPatch,
    FinanceTaxInfo,
    FinanceTotals,
    RecurringExpenseCreateBody,
    RecurringExpenseItem,
    RecurringExpensePatchBody,
)
from app.infrastructure.persistence.models.app_setting import AppSetting
from app.infrastructure.persistence.models.expense import Expense
from app.infrastructure.persistence.models.expense_category import ExpenseCategory
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

    months = [str(m) for m in (raw.get("months") or [])]
    n = len(months)

    gross = _decimal_list(raw.get("revenue_gross"), n)
    net = _decimal_list(raw.get("revenue_net"), n)
    commission = _decimal_list(raw.get("psp_commission"), n)
    gross_sub = _decimal_list(raw.get("revenue_gross_subscription"), n)
    gross_one = _decimal_list(raw.get("revenue_gross_one_time"), n)
    expenses = _decimal_list(raw.get("expenses_total"), n)

    rate = settings.tax_rate
    tax_zero = settings.tax_mode == "none" or rate == 0

    tax: list[Decimal] = []
    profit: list[Decimal] = []
    for i in range(n):
        if tax_zero:
            base = Decimal(0)
        elif settings.tax_base == "gross":
            base = gross[i]
        elif settings.tax_base == "net":
            base = net[i]
        else:  # profit
            base = max(Decimal(0), net[i] - expenses[i])
        t = (base * rate) if not tax_zero else Decimal(0)
        if t < 0:
            t = Decimal(0)
        tax.append(t)
        profit.append(net[i] - expenses[i] - t)

    # Итоги
    total_gross = sum(gross, Decimal(0))
    total_net = sum(net, Decimal(0))
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
            expenses_total=_money_str(total_expenses),
            tax=_money_str(total_tax),
            profit_net=_money_str(total_profit),
            margin_percent=str(margin.quantize(Decimal("0.1"))),
            payment_count=payment_count,
        ),
        tax=FinanceTaxInfo(mode=settings.tax_mode, rate=str(rate), base=settings.tax_base),
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
    row = Expense(
        incurred_on=body.incurred_on,
        amount=body.amount,
        category_id=body.category_id,
        title=body.title.strip(),
        note=(body.note or None),
        created_by=_current_user_id(),
    )
    session.add(row)
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
