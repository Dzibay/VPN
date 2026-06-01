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
    RecurringExpenseCreateBody,
    RecurringExpenseItem,
    RecurringExpensePatchBody,
    RecurringExpensesListResponse,
)
from app.domain.services.accounting_service import (
    create_category,
    create_expense,
    create_recurring_expense,
    delete_category,
    delete_expenses_by_ids,
    delete_recurring_expense,
    get_accounting_summary,
    get_finance_settings,
    list_categories,
    list_expenses,
    list_recurring_expenses,
    update_category,
    update_expense,
    update_finance_settings,
    update_recurring_expense,
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
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "category_not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Категория не найдена",
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
