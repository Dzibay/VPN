from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    StaffUserListMode,
    require_admin,
    require_referrals_staff,
    require_staff_user_list_access,
)
from app.core.exceptions import ForbiddenError
from app.domain.models.server_traffic import UserTrafficByDayRow, UserTrafficByServersBundle
from app.domain.models.user_balance import UserBalanceLedgerListResponse
from app.domain.models.users import (
    DailyPaymentsExpiryDayDetailResponse,
    DailyPaymentsExpiryStatsResponse,
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    StaffUserSearchItem,
    StaffUsersBulkDeleteBody,
    StaffUsersBulkDeleteResponse,
    StaffUsersListResponse,
    UserCreate,
    UserListItem,
    UserRead,
    UsersCountResponse,
    UsersDailyStatsResponse,
    UserUpdate,
)
from app.domain.services.users_service import (
    create_staff_user,
    delete_staff_user,
    delete_staff_users_bulk,
    extend_active_subscriptions,
    patch_staff_user,
    require_user_exists,
    search_staff_users,
    staff_get_user_list_item,
    staff_list_users,
    users_count,
)
from app.domain.users.daily_stats import (
    daily_payments_expiry_day_detail,
    daily_payments_expiry_stats,
    users_daily_stats,
)
from app.domain.users.staff_balance_ledger import staff_user_balance_ledger
from app.domain.users.traffic_breakdown import (
    user_traffic_by_servers_bundle,
    user_traffic_cumulative_by_day_rows,
)
from app.domain.users.xray_sync_queue import enqueue_sync_xray_clients_all_servers
from app.infrastructure.persistence.models.user import User

router = APIRouter(
    prefix="/users",
    tags=["admin"],
)


@router.get(
    "/count",
    response_model=UsersCountResponse,
    summary="Число записей пользователей в базе и сводка по регистрациям (виджеты админки)",
)
async def users_count_ep(
    session: ReadonlySessionDep,
    _: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> UsersCountResponse:
    return await users_count(session)


@router.get(
    "",
    response_model=StaffUsersListResponse,
    summary=(
        "Пагинированный список пользователей для административного и менеджерского интерфейса; "
        "токен подписки и UUID VLESS возвращаются только при доступе администратора. "
        "Параметр referral_link_id — только пользователи, у которых при регистрации "
        "зафиксирована указанная реферальная ссылка."
    ),
)
async def list_users(
    session: ReadonlySessionDep,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
    referral_link_id: Annotated[
        int | None,
        Query(
            ge=1,
            description=(
                "Если указан — только пользователи с таким users.referral_link_id "
                "(пришли по этой реферальной ссылке при регистрации)"
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Размер страницы (по умолчанию 50)"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Смещение от начала списка"),
    ] = 0,
    sort_by: Annotated[
        Literal[
            "id",
            "email",
            "telegram",
            "role",
            "registered_at",
            "subscription_until",
            "subscription",
            "traffic",
            "devices",
            "referral_link_id",
        ]
        | None,
        Query(description="Столбец сортировки; без параметра — id по убыванию"),
    ] = None,
    sort_dir: Annotated[
        Literal["asc", "desc"],
        Query(description="Направление сортировки (при sort_by)"),
    ] = "asc",
) -> StaffUsersListResponse:
    show_secrets = list_mode in ("open", "admin")
    return await staff_list_users(
        session,
        show_secrets=show_secrets,
        referral_link_id=referral_link_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.delete(
    "/bulk",
    response_model=StaffUsersBulkDeleteResponse,
    dependencies=[Depends(require_admin)],
    summary="Массовое удаление пользователей (только admin)",
)
async def delete_users_bulk(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    body: StaffUsersBulkDeleteBody,
) -> StaffUsersBulkDeleteResponse:
    deleted = await delete_staff_users_bulk(session, ids=body.ids)
    if deleted:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return StaffUsersBulkDeleteResponse(deleted_count=deleted)


@router.get(
    "/search",
    response_model=list[StaffUserSearchItem],
    dependencies=[Depends(require_referrals_staff)],
    summary="Поиск пользователей (email, id, telegram_id, все значения telegram_properties)",
)
async def staff_search_users(
    session: ReadonlySessionDep,
    q: Annotated[
        str,
        Query(
            min_length=3,
            max_length=100,
            description="Подстрока без учёта регистра; от 3 символов",
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=50, description="Максимум строк в ответе")] = 30,
) -> list[StaffUserSearchItem]:
    return await search_staff_users(session, q=q, limit=limit)


@router.get(
    "/daily-stats",
    response_model=UsersDailyStatsResponse,
    dependencies=[Depends(require_referrals_staff)],
    summary="Статистика: по дням МСК или по часам суток Москвы (granularity); время в JSON — Москва",
)
async def users_daily_stats_ep(
    session: ReadonlySessionDep,
    granularity: Annotated[
        Literal["day", "hour"],
        Query(
            description=(
                "day — по календарным дням Europe/Moscow; hour — 24 часа календарного дня Europe/Moscow (hour_day обязателен)"
            ),
        ),
    ] = "day",
    hour_day: Annotated[
        date | None,
        Query(
            description="При granularity=hour — календарная дата суток по Москве YYYY-MM-DD",
        ),
    ] = None,
) -> UsersDailyStatsResponse:
    if granularity == "hour" and hour_day is None:
        raise HTTPException(
            status_code=422,
            detail="Укажите hour_day (календарный день по Москве, YYYY-MM-DD) для granularity=hour",
        )
    try:
        return await users_daily_stats(
            session,
            granularity=granularity,
            hour_day=hour_day,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get(
    "/daily-payments-expiry-bars",
    response_model=DailyPaymentsExpiryStatsResponse,
    dependencies=[Depends(require_referrals_staff)],
    summary="Оплаты, трафик/активные за день и окончания подписки по дням МСК (столбчатый график)",
)
async def daily_payments_expiry_bars_ep(
    session: ReadonlySessionDep,
    month: Annotated[
        str | None,
        Query(
            description="Календарный месяц Europe/Moscow в виде YYYY-MM; если не указан — все дни в диапазоне данных",
        ),
    ] = None,
) -> DailyPaymentsExpiryStatsResponse:
    try:
        bundle = await daily_payments_expiry_stats(session, month=month)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return DailyPaymentsExpiryStatsResponse(
        rows=bundle.rows,
        month_min=bundle.month_min,
        month_max=bundle.month_max,
    )


@router.get(
    "/daily-payments-expiry-bars/detail",
    response_model=DailyPaymentsExpiryDayDetailResponse,
    dependencies=[Depends(require_referrals_staff)],
    summary="Детализация по дню МСК: пользователи и платежи для столбчатого графика оплат/окончаний",
)
async def daily_payments_expiry_day_detail_ep(
    session: ReadonlySessionDep,
    day: Annotated[
        date,
        Query(description="Календарный день Europe/Moscow (YYYY-MM-DD)"),
    ],
) -> DailyPaymentsExpiryDayDetailResponse:
    return await daily_payments_expiry_day_detail(session, day=day)


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(require_admin)],
    summary="Создание пользователя; токен подписки и UUID генерируются на сервере",
)
async def create_user(
    body: UserCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    user = await create_staff_user(session, body)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user


@router.post(
    "/extend-active-subscriptions",
    response_model=ExtendActiveSubscriptionsResponse,
    dependencies=[Depends(require_admin)],
    summary=(
        "Продление подписки на указанное число календарных дней для всех записей "
        "с активной конечной датой; пользователи без срока подписки не изменяются"
    ),
)
async def extend_active_subscriptions_ep(
    body: ExtendActiveSubscriptionsBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> ExtendActiveSubscriptionsResponse:
    resp = await extend_active_subscriptions(session, body)
    if resp.updated_count:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.get(
    "/{user_id}",
    response_model=UserListItem,
    summary="Карточка пользователя для админки (как строка в списке /users)",
)
async def get_staff_user(
    user_id: int,
    session: ReadonlySessionDep,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> UserListItem:
    show_secrets = list_mode in ("open", "admin")
    return await staff_get_user_list_item(session, user_id, show_secrets=show_secrets)


@router.get(
    "/{user_id}/balance-ledger",
    response_model=UserBalanceLedgerListResponse,
    dependencies=[Depends(require_referrals_staff)],
    summary="Журнал операций баланса пользователя (начисления реферальных бонусов и др.)",
)
async def user_balance_ledger_ep(
    user_id: int,
    session: ReadonlySessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserBalanceLedgerListResponse:
    return await staff_user_balance_ledger(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{user_id}/traffic-by-server",
    response_model=UserTrafficByServersBundle,
    dependencies=[Depends(require_referrals_staff)],
    summary="Трафик пользователя по узлам (данные из базы)",
)
async def user_traffic_by_server(
    user_id: int,
    session: ReadonlySessionDep,
) -> UserTrafficByServersBundle:
    return await user_traffic_by_servers_bundle(session, user_id)


@router.get(
    "/{user_id}/traffic-by-day",
    response_model=list[UserTrafficByDayRow],
    dependencies=[Depends(require_referrals_staff)],
    summary="Накопительный трафик по календарным дням (UTC)",
)
async def user_traffic_by_day(
    user_id: int,
    session: ReadonlySessionDep,
) -> list[UserTrafficByDayRow]:
    await require_user_exists(session, user_id)
    return await user_traffic_cumulative_by_day_rows(session, user_id)


@router.delete(
    "/{user_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
    summary="Удаление пользователя и синхронизация списка клиентов на узлах",
)
async def delete_user(
    user_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> None:
    await delete_staff_user(session, user_id)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)


@router.patch(
    "/{user_id}",
    response_model=UserListItem,
    dependencies=[Depends(require_referrals_staff)],
    summary=(
        "Частичное обновление пользователя и синхронизация Xray на узлах; "
        "менеджер может менять только traffic_limit_bytes"
    ),
)
async def patch_user(
    user_id: int,
    body: UserUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> UserListItem:
    if list_mode == "manager":
        extra = set(body.model_dump(exclude_unset=True)) - {"traffic_limit_bytes"}
        if extra:
            raise ForbiddenError(
                detail="Менеджер может изменять только лимит трафика (traffic_limit_bytes)",
            )
    await patch_staff_user(session, user_id, body)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    show_secrets = list_mode in ("open", "admin")
    return await staff_get_user_list_item(session, user_id, show_secrets=show_secrets)
