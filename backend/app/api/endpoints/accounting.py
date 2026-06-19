"""Админка: бухгалтерия (P&L) — сводка, расходы, повторяющиеся шаблоны, категории, налог.

Доступ: чтение и операционные записи — admin или manager (require_referrals_staff);
изменение настроек/категорий и массовое удаление — только admin.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    require_admin,
    require_referrals_staff,
)
from app.core.exceptions import BadRequestError
from app.core.time import moscow_today
from app.domain.models.accounting import (
    CashAccountCreateBody,
    CashAccountItem,
    CashAccountPatchBody,
    CashAccountsListResponse,
    CashTransactionCreateBody,
    CashTransactionItem,
    CashTransactionsListResponse,
    ExpenseCategoriesListResponse,
    ExpenseCategoryCreateBody,
    ExpenseCategoryItem,
    ExpenseCategoryPatchBody,
    ExpenseCreateBody,
    ExpenseItem,
    ExpensePatchBody,
    ExpensesBulkDeleteBody,
    ExpensesBulkDeleteResponse,
    ExpensesListResponse,
    FinanceAccountingSummaryResponse,
    FinanceSettings,
    FinanceSettingsPatch,
    PayableCreateBody,
    PayableItem,
    PayablePatchBody,
    PayablePaymentBody,
    PayablesListResponse,
    ProfitWithdrawalCreateBody,
    ProfitWithdrawalItem,
    ProfitWithdrawalPatchBody,
    ProfitWithdrawalsListResponse,
    RecurringExpenseCreateBody,
    RecurringExpenseItem,
    RecurringExpensePatchBody,
    RecurringExpensesListResponse,
    RefundCreateBody,
    RefundItem,
    RefundPatchBody,
    RefundsListResponse,
)
from app.domain.services.accounting_service import (
    create_cash_account,
    create_cash_transaction,
    create_category,
    create_expense,
    create_payable,
    create_profit_withdrawal,
    create_recurring_expense,
    create_refund,
    delete_category,
    delete_expenses_by_ids,
    delete_payable,
    delete_recurring_expense,
    get_accounting_summary,
    get_finance_settings,
    list_cash_accounts,
    list_cash_transactions,
    list_categories,
    list_expenses,
    list_payables,
    list_profit_withdrawals,
    list_recurring_expenses,
    list_refunds,
    pay_payable,
    update_cash_account,
    update_category,
    update_expense,
    update_finance_settings,
    update_payable,
    update_profit_withdrawal,
    update_recurring_expense,
    update_refund,
)

accounting_router = APIRouter(
    prefix="/admin/accounting",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


def _default_range() -> tuple[date, date]:
    today = moscow_today()
    return date(today.year, 1, 1), today


# --------------------------------------------------------------------------- #
# Сводка
# --------------------------------------------------------------------------- #
@accounting_router.get(
    "/summary",
    response_model=FinanceAccountingSummaryResponse,
    summary="Сводка бухгалтерии (P&L) по месяцам в диапазоне",
    description="Помесячно: выручка (валовая/чистая), комиссии PSP, расходы по категориям, "
    "налог и чистая прибыль. Расходы — разовые + развёрнутые повторяющиеся шаблоны. "
    "По умолчанию диапазон — с 1 января текущего года по сегодня (Москва).",
)
async def accounting_summary(
    session: ReadonlySessionDep,
    date_from: Annotated[date | None, Query(alias="from", description="YYYY-MM-DD")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="YYYY-MM-DD")] = None,
) -> FinanceAccountingSummaryResponse:
    d_from, d_to = _default_range()
    if date_from is not None:
        d_from = date_from
    if date_to is not None:
        d_to = date_to
    if d_from > d_to:
        raise BadRequestError("Начало диапазона позже его конца")
    return await get_accounting_summary(session, date_from=d_from, date_to=d_to)


# --------------------------------------------------------------------------- #
# Налоговые настройки
# --------------------------------------------------------------------------- #
@accounting_router.get(
    "/settings",
    response_model=FinanceSettings,
    summary="Текущие налоговые настройки",
)
async def get_settings(session: ReadonlySessionDep) -> FinanceSettings:
    return await get_finance_settings(session)


@accounting_router.patch(
    "/settings",
    response_model=FinanceSettings,
    dependencies=[Depends(require_admin)],
    summary="Изменить налоговые настройки (только admin)",
)
async def patch_settings(
    session: SessionDep,
    body: FinanceSettingsPatch,
) -> FinanceSettings:
    return await update_finance_settings(session, body)


# --------------------------------------------------------------------------- #
# Категории
# --------------------------------------------------------------------------- #
@accounting_router.get(
    "/categories",
    response_model=ExpenseCategoriesListResponse,
    summary="Список категорий расходов",
)
async def get_categories(
    session: ReadonlySessionDep,
    include_archived: Annotated[bool, Query(description="Включая архивные")] = True,
) -> ExpenseCategoriesListResponse:
    items = await list_categories(session, include_archived=include_archived)
    return ExpenseCategoriesListResponse(items=items)


@accounting_router.post(
    "/categories",
    response_model=ExpenseCategoryItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
    summary="Создать категорию (только admin)",
)
async def post_category(
    session: SessionDep,
    body: ExpenseCategoryCreateBody,
) -> ExpenseCategoryItem:
    try:
        return await create_category(session, body)
    except LookupError as err:
        if (err.args[0] if err.args else "") == "slug_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Категория с таким slug уже существует",
            ) from err
        raise


@accounting_router.patch(
    "/categories/{category_id}",
    response_model=ExpenseCategoryItem,
    dependencies=[Depends(require_admin)],
    summary="Изменить категорию (только admin)",
)
async def patch_category(
    session: SessionDep,
    category_id: Annotated[int, Path(ge=1)],
    body: ExpenseCategoryPatchBody,
) -> ExpenseCategoryItem:
    try:
        return await update_category(session, category_id, body)
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from err


@accounting_router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Удалить категорию (только admin)",
)
async def remove_category(
    session: SessionDep,
    category_id: Annotated[int, Path(ge=1)],
) -> None:
    try:
        await delete_category(session, category_id)
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from err


# --------------------------------------------------------------------------- #
# Разовые расходы
# --------------------------------------------------------------------------- #
@accounting_router.get(
    "/expenses",
    response_model=ExpensesListResponse,
    summary="Список разовых расходов",
)
async def get_expenses(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ExpensesListResponse:
    items, total = await list_expenses(
        session, limit=limit, offset=offset, date_from=date_from, date_to=date_to
    )
    return ExpensesListResponse(items=items, total=total, limit=limit, offset=offset)


@accounting_router.post(
    "/expenses",
    response_model=ExpenseItem,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить разовый расход",
)
async def post_expense(session: SessionDep, body: ExpenseCreateBody) -> ExpenseItem:
    try:
        return await create_expense(session, body)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для расхода, оплаченного человеком, укажите кто оплатил",
        ) from err
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Категория не найдена",
        ) from err


@accounting_router.patch(
    "/expenses/{expense_id}",
    response_model=ExpenseItem,
    summary="Изменить разовый расход",
)
async def patch_expense(
    session: SessionDep,
    expense_id: Annotated[int, Path(ge=1)],
    body: ExpensePatchBody,
) -> ExpenseItem:
    try:
        return await update_expense(session, expense_id, body)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для расхода, оплаченного человеком, укажите кто оплатил",
        ) from err
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code in {"category_not_found", "cash_account_not_found"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Категория или счет не найдены",
            ) from err
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Расход не найден",
        ) from err


@accounting_router.delete(
    "/expenses",
    response_model=ExpensesBulkDeleteResponse,
    dependencies=[Depends(require_admin)],
    summary="Удалить выбранные расходы (только admin)",
)
async def delete_expenses(
    session: SessionDep,
    body: ExpensesBulkDeleteBody,
) -> ExpensesBulkDeleteResponse:
    if not body.ids:
        raise BadRequestError("Нужно передать хотя бы один id")
    deleted = await delete_expenses_by_ids(session, ids=body.ids)
    return ExpensesBulkDeleteResponse(deleted_count=deleted)


# --------------------------------------------------------------------------- #
# Повторяющиеся расходы (шаблоны)
# --------------------------------------------------------------------------- #
@accounting_router.get(
    "/recurring-expenses",
    response_model=RecurringExpensesListResponse,
    summary="Список повторяющихся расходов (шаблонов)",
)
async def get_recurring(session: ReadonlySessionDep) -> RecurringExpensesListResponse:
    items = await list_recurring_expenses(session)
    return RecurringExpensesListResponse(items=items)


@accounting_router.post(
    "/recurring-expenses",
    response_model=RecurringExpenseItem,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить повторяющийся расход",
)
async def post_recurring(
    session: SessionDep,
    body: RecurringExpenseCreateBody,
) -> RecurringExpenseItem:
    try:
        return await create_recurring_expense(session, body)
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Категория не найдена",
        ) from err


@accounting_router.patch(
    "/recurring-expenses/{recurring_id}",
    response_model=RecurringExpenseItem,
    summary="Изменить повторяющийся расход",
)
async def patch_recurring(
    session: SessionDep,
    recurring_id: Annotated[int, Path(ge=1)],
    body: RecurringExpensePatchBody,
) -> RecurringExpenseItem:
    try:
        return await update_recurring_expense(session, recurring_id, body)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Конец периода не может быть раньше начала",
        ) from err
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "category_not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Категория не найдена",
            ) from err
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Шаблон не найден",
        ) from err


@accounting_router.delete(
    "/recurring-expenses/{recurring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Удалить повторяющийся расход (только admin)",
)
async def remove_recurring(
    session: SessionDep,
    recurring_id: Annotated[int, Path(ge=1)],
) -> None:
    try:
        await delete_recurring_expense(session, recurring_id)
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Шаблон не найден",
        ) from err


# --------------------------------------------------------------------------- #
# Счета, долги, возвраты, вывод прибыли
# --------------------------------------------------------------------------- #
@accounting_router.get("/cash-accounts", response_model=CashAccountsListResponse)
async def get_cash_accounts(session: ReadonlySessionDep) -> CashAccountsListResponse:
    return CashAccountsListResponse(items=await list_cash_accounts(session))


@accounting_router.post(
    "/cash-accounts",
    response_model=CashAccountItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def post_cash_account(session: SessionDep, body: CashAccountCreateBody) -> CashAccountItem:
    return await create_cash_account(session, body)


@accounting_router.patch(
    "/cash-accounts/{account_id}",
    response_model=CashAccountItem,
    dependencies=[Depends(require_admin)],
)
async def patch_cash_account(
    session: SessionDep,
    account_id: Annotated[int, Path(ge=1)],
    body: CashAccountPatchBody,
) -> CashAccountItem:
    try:
        return await update_cash_account(session, account_id, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден") from err


@accounting_router.get("/cash-transactions", response_model=CashTransactionsListResponse)
async def get_cash_transactions(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CashTransactionsListResponse:
    items, total = await list_cash_transactions(session, limit=limit, offset=offset)
    return CashTransactionsListResponse(items=items, total=total, limit=limit, offset=offset)


@accounting_router.post(
    "/cash-transactions",
    response_model=CashTransactionItem,
    status_code=status.HTTP_201_CREATED,
)
async def post_cash_transaction(
    session: SessionDep,
    body: CashTransactionCreateBody,
) -> CashTransactionItem:
    try:
        return await create_cash_transaction(session, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Счет не найден") from err


@accounting_router.get("/payables", response_model=PayablesListResponse)
async def get_payables(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> PayablesListResponse:
    items, total = await list_payables(
        session,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )
    return PayablesListResponse(items=items, total=total, limit=limit, offset=offset)


@accounting_router.post(
    "/payables",
    response_model=PayableItem,
    status_code=status.HTTP_201_CREATED,
)
async def post_payable(session: SessionDep, body: PayableCreateBody) -> PayableItem:
    return await create_payable(session, body)


@accounting_router.patch("/payables/{payable_id}", response_model=PayableItem)
async def patch_payable(
    session: SessionDep,
    payable_id: Annotated[int, Path(ge=1)],
    body: PayablePatchBody,
) -> PayableItem:
    try:
        return await update_payable(session, payable_id, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Долг не найден") from err


@accounting_router.post("/payables/{payable_id}/payments", response_model=PayableItem)
async def post_payable_payment(
    session: SessionDep,
    payable_id: Annotated[int, Path(ge=1)],
    body: PayablePaymentBody,
) -> PayableItem:
    try:
        return await pay_payable(session, payable_id, body)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная сумма выплаты") from err
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Долг или счет не найден") from err


@accounting_router.delete(
    "/payables/{payable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Удалить долг (только admin; выплаты сохраняются в cash-корректировке)",
)
async def remove_payable(
    session: SessionDep,
    payable_id: Annotated[int, Path(ge=1)],
) -> None:
    try:
        await delete_payable(session, payable_id)
    except ValueError as err:
        code = err.args[0] if err.args else ""
        if code == "no_cash_account":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нужен хотя бы один активный счёт для сохранения уже проведённых выплат в cash",
            ) from err
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная операция") from err
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Долг не найден",
        ) from err


@accounting_router.get("/refunds", response_model=RefundsListResponse)
async def get_refunds(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RefundsListResponse:
    items, total = await list_refunds(session, limit=limit, offset=offset)
    return RefundsListResponse(items=items, total=total, limit=limit, offset=offset)


@accounting_router.post("/refunds", response_model=RefundItem, status_code=status.HTTP_201_CREATED)
async def post_refund(session: SessionDep, body: RefundCreateBody) -> RefundItem:
    try:
        return await create_refund(session, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Счет не найден") from err


@accounting_router.patch("/refunds/{refund_id}", response_model=RefundItem)
async def patch_refund(
    session: SessionDep,
    refund_id: Annotated[int, Path(ge=1)],
    body: RefundPatchBody,
) -> RefundItem:
    try:
        return await update_refund(session, refund_id, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Возврат не найден") from err


@accounting_router.get("/profit-withdrawals", response_model=ProfitWithdrawalsListResponse)
async def get_profit_withdrawals(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProfitWithdrawalsListResponse:
    items, total = await list_profit_withdrawals(session, limit=limit, offset=offset)
    return ProfitWithdrawalsListResponse(items=items, total=total, limit=limit, offset=offset)


@accounting_router.post(
    "/profit-withdrawals",
    response_model=ProfitWithdrawalItem,
    status_code=status.HTTP_201_CREATED,
)
async def post_profit_withdrawal(
    session: SessionDep,
    body: ProfitWithdrawalCreateBody,
) -> ProfitWithdrawalItem:
    try:
        return await create_profit_withdrawal(session, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Счет не найден") from err


@accounting_router.patch(
    "/profit-withdrawals/{withdrawal_id}",
    response_model=ProfitWithdrawalItem,
)
async def patch_profit_withdrawal(
    session: SessionDep,
    withdrawal_id: Annotated[int, Path(ge=1)],
    body: ProfitWithdrawalPatchBody,
) -> ProfitWithdrawalItem:
    try:
        return await update_profit_withdrawal(session, withdrawal_id, body)
    except LookupError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вывод не найден") from err
