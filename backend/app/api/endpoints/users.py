from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    StaffUserListMode,
    require_admin,
    require_referrals_staff,
    require_staff_user_list_access,
)
from app.domain.models.server_traffic import UserTrafficByDayRow, UserTrafficByServersBundle
from app.domain.models.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    UserCreate,
    UserListItem,
    UserRead,
    UsersCountResponse,
    UsersDailyStatsResponse,
    UserUpdate,
)
from app.domain.services.http_errors import HttpServiceError
from app.infrastructure.persistence.models.user import User
from app.domain.services.users_service import (
    create_staff_user,
    delete_staff_user,
    enqueue_sync_xray_clients_all_servers,
    extend_active_subscriptions,
    patch_staff_user,
    require_user_exists,
    staff_list_users,
    user_traffic_by_servers_bundle,
    user_traffic_cumulative_by_day_rows,
    users_count,
    users_daily_stats,
)

router = APIRouter(
    prefix="/users",
    tags=["admin"],
)


def _raise_svc(exc: HttpServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/count",
    response_model=UsersCountResponse,
    dependencies=[Depends(require_admin)],
    summary="Число записей пользователей в базе данных",
)
async def users_count_ep(session: ReadonlySessionDep) -> UsersCountResponse:
    return users_count(session)


@router.get(
    "",
    response_model=list[UserListItem],
    summary=(
        "Список пользователей для административного и менеджерского интерфейса; "
        "токен подписки и UUID VLESS возвращаются только при доступе администратора"
    ),
)
async def list_users(
    session: ReadonlySessionDep,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> list[UserListItem]:
    show_secrets = list_mode in ("open", "admin")
    return staff_list_users(session, show_secrets=show_secrets)


@router.get(
    "/daily-stats",
    response_model=UsersDailyStatsResponse,
    dependencies=[Depends(require_referrals_staff)],
    summary="Дневная статистика (UTC): регистрации, трафик, устройства подписки и активность по датам",
)
async def users_daily_stats_ep(session: ReadonlySessionDep) -> UsersDailyStatsResponse:
    return users_daily_stats(session)


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
    try:
        user = create_staff_user(session, body)
    except HttpServiceError as e:
        _raise_svc(e)
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
    resp = extend_active_subscriptions(session, body)
    if resp.updated_count:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.get(
    "/{user_id}/traffic-by-server",
    response_model=UserTrafficByServersBundle,
    dependencies=[Depends(require_admin)],
    summary="Трафик пользователя по узлам (данные из базы)",
)
async def user_traffic_by_server(
    user_id: int,
    session: ReadonlySessionDep,
) -> UserTrafficByServersBundle:
    try:
        return user_traffic_by_servers_bundle(session, user_id)
    except HttpServiceError as e:
        _raise_svc(e)


@router.get(
    "/{user_id}/traffic-by-day",
    response_model=list[UserTrafficByDayRow],
    dependencies=[Depends(require_admin)],
    summary="Накопительный трафик по календарным дням (UTC)",
)
async def user_traffic_by_day(
    user_id: int,
    session: ReadonlySessionDep,
) -> list[UserTrafficByDayRow]:
    try:
        require_user_exists(session, user_id)
    except HttpServiceError as e:
        _raise_svc(e)
    return user_traffic_cumulative_by_day_rows(session, user_id)


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
    try:
        delete_staff_user(session, user_id)
    except HttpServiceError as e:
        _raise_svc(e)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_admin)],
    summary="Частичное обновление пользователя и синхронизация Xray на узлах",
)
async def patch_user(
    user_id: int,
    body: UserUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    try:
        user = patch_staff_user(session, user_id, body)
    except HttpServiceError as e:
        _raise_svc(e)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user
