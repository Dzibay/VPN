"""Админка: списки payments и tasks (JWT admin или manager)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, SessionDep, require_admin, require_referrals_staff
from app.core.exceptions import BadRequestError
from app.domain.models.staff_ledger import (
    StaffCreateTaskBody,
    StaffCreateTributePaymentBody,
    StaffCreateTributePaymentResponse,
    StaffPatchTaskBody,
    StaffPaymentsBulkDeleteBody,
    StaffPaymentsBulkDeleteResponse,
    StaffPaymentsFinanceSummaryResponse,
    StaffPaymentsListResponse,
    StaffTaskItem,
    StaffTasksListResponse,
)
from app.domain.services.staff_ledger_service import (
    create_staff_task,
    create_staff_manual_payment_record,
    delete_staff_task,
    get_staff_task,
    list_staff_payments,
    list_staff_tasks,
    staff_delete_payments_by_ids,
    staff_payments_finance_summary,
    update_staff_task,
)

payments_staff_router = APIRouter(
    prefix="/admin/payments",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)

tasks_staff_router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@payments_staff_router.get(
    "/finance-summary",
    response_model=StaffPaymentsFinanceSummaryResponse,
    summary="Сводка платежей по месяцам и типу (RPC)",
    description="Агрегат ``rpc_staff_payments_finance_summary()``: общая ось ``months`` (UTC). "
    "``cash`` — полная сумма в месяце даты платежа. ``spread`` — сумма ``amount/months`` "
    "в месяце платежа и в каждом из следующих ``months-1`` календарных месяцев.",
)
async def staff_payments_finance_summary_endpoint(
    session: ReadonlySessionDep,
) -> StaffPaymentsFinanceSummaryResponse:
    return await staff_payments_finance_summary(session)


@payments_staff_router.get(
    "",
    response_model=StaffPaymentsListResponse,
    summary="Список платежей (payments)",
)
async def staff_list_payments(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000, description="Максимум строк в ответе")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение от новых к старым")] = 0,
    user_id: Annotated[
        int | None,
        Query(ge=1, description="Только платежи этого пользователя (users.id)"),
    ] = None,
) -> StaffPaymentsListResponse:
    items, total = await list_staff_payments(
        session, limit=limit, offset=offset, user_id=user_id
    )
    return StaffPaymentsListResponse(items=items, total=total, limit=limit, offset=offset)


@payments_staff_router.post(
    "",
    response_model=StaffCreateTributePaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать ручной платёж (provider=manual)",
    description="Продлевает подписку, пишет payments (provider=manual), notify_payment и реферальные бонусы. "
    "Telegram не обязателен.",
)
async def staff_create_manual_payment(
    session: SessionDep,
    body: StaffCreateTributePaymentBody,
) -> StaffCreateTributePaymentResponse:
    try:
        return await create_staff_manual_payment_record(
            session,
            settings,
            user_id=body.user_id,
            months=body.months,
            amount_rub=body.amount_rub,
            payment_kind=body.payment_kind,
            created_at=body.created_at,
        )
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "user_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь с таким user_id не найден",
            ) from err
        raise


@payments_staff_router.delete(
    "",
    response_model=StaffPaymentsBulkDeleteResponse,
    dependencies=[Depends(require_admin)],
    summary="Удаление выбранных платежей по списку id (только admin)",
)
async def staff_delete_payments(
    session: SessionDep,
    body: StaffPaymentsBulkDeleteBody,
) -> StaffPaymentsBulkDeleteResponse:
    if not body.ids:
        raise BadRequestError("Нужно передать хотя бы один id")
    deleted = await staff_delete_payments_by_ids(session, ids=body.ids)
    return StaffPaymentsBulkDeleteResponse(deleted_count=deleted)


@tasks_staff_router.get(
    "",
    response_model=StaffTasksListResponse,
    summary="Список задач (tasks)",
)
async def staff_list_tasks(
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=5000, description="Максимум строк в ответе")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение от новых к старым")] = 0,
    user_id: Annotated[
        int | None,
        Query(ge=1, description="Только задачи с этим user_id"),
    ] = None,
) -> StaffTasksListResponse:
    items, total = await list_staff_tasks(session, limit=limit, offset=offset, user_id=user_id)
    return StaffTasksListResponse(items=items, total=total, limit=limit, offset=offset)


@tasks_staff_router.get(
    "/{task_id}",
    response_model=StaffTaskItem,
    summary="Одна задача по id (для открытия формы из других экранов)",
)
async def staff_get_task(
    session: ReadonlySessionDep,
    task_id: Annotated[int, Path(ge=1, description="tasks.id")],
) -> StaffTaskItem:
    row = await get_staff_task(session, task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )
    return row


@tasks_staff_router.post(
    "",
    response_model=StaffTaskItem,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задачу (tasks)",
    description="Типы и поля как в схеме БД; очередь Telegram-бота — для типов из notification-tasks.",
)
async def staff_create_task(
    session: SessionDep,
    body: StaffCreateTaskBody,
) -> StaffTaskItem:
    try:
        return await create_staff_task(
            session,
            user_id=body.user_id,
            task_type=body.task_type,
            referee_id=body.referee_id,
            bonus_days=body.bonus_days,
            paid_months=body.paid_months,
        )
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "user_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь с таким user_id не найден",
            ) from err
        if code == "referee_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь с таким referee_id не найден",
            ) from err
        raise


@tasks_staff_router.patch(
    "/{task_id}",
    response_model=StaffTaskItem,
    summary="Обновить задачу (tasks)",
    description="Частичное обновление: передайте только меняемые поля. Статус: при смене на completed/failed "
    "без done_at выставляется текущее время UTC; на pending — done_at сбрасывается.",
)
async def staff_patch_task(
    session: SessionDep,
    task_id: Annotated[int, Path(ge=1, description="tasks.id")],
    body: StaffPatchTaskBody,
) -> StaffTaskItem:
    try:
        return await update_staff_task(session, task_id, body)
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "task_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена",
            ) from err
        if code == "user_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь с таким user_id не найден",
            ) from err
        if code == "referee_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь с таким referee_id не найден",
            ) from err
        raise


@tasks_staff_router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Удалить задачу (только admin)",
)
async def staff_delete_task(
    session: SessionDep,
    task_id: Annotated[int, Path(ge=1, description="tasks.id")],
) -> None:
    try:
        await delete_staff_task(session, task_id)
    except LookupError as err:
        code = err.args[0] if err.args else ""
        if code == "task_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена",
            ) from err
        raise
