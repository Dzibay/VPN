import logging
from datetime import date
from typing import Annotated, Literal, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    ReadonlySessionDep,
    SessionDep,
    StaffUserListMode,
    require_admin,
    require_staff_user_list_access,
)
from app.database.operations import table_insert
from app.models.server import Server
from app.models.user import User
from app.models.user_server_traffic import UserServerTraffic
from app.schemas.server_traffic import UserTrafficByServersBundle, UserTrafficPerServerRow
from app.schemas.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    UserCreate,
    UserListItem,
    UserRead,
    UsersCountResponse,
    UserUpdate,
)
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.users")

router = APIRouter(
    prefix="/users",
    tags=["admin"],
)


def _normalize_account_role(raw: str | None) -> str:
    r = (raw or "client").strip()
    if r in ("client", "manager", "admin"):
        return r
    return "client"


def _user_rows_with_traffic(session: Session) -> list[tuple[User, int]]:
    traffic_agg = (
        select(
            UserServerTraffic.user_id.label("uid"),
            func.coalesce(
                func.sum(UserServerTraffic.up_bytes + UserServerTraffic.down_bytes),
                0,
            ).label("total_bytes"),
        )
        .group_by(UserServerTraffic.user_id)
        .subquery()
    )
    stmt = (
        select(User, func.coalesce(traffic_agg.c.total_bytes, 0).label("total_traffic"))
        .outerjoin(traffic_agg, User.id == traffic_agg.c.uid)
        .order_by(User.id.desc())
    )
    return list(session.execute(stmt).all())


@router.get(
    "/count",
    response_model=UsersCountResponse,
    dependencies=[Depends(require_admin)],
    summary="Количество пользователей в БД",
)
async def users_count(session: ReadonlySessionDep) -> UsersCountResponse:
    total = session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


@router.get(
    "",
    response_model=list[UserListItem],
    summary=(
        "Список пользователей для таблиц админа и менеджера: трафик и реферал; "
        "токен подписки и vless — только у админа (или при выключенном JWT-гейте)"
    ),
)
async def list_users(
    session: ReadonlySessionDep,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> list[UserListItem]:
    show_secrets = list_mode in ("open", "admin")
    rows = _user_rows_with_traffic(session)
    out: list[UserListItem] = []
    for user, total_raw in rows:
        try:
            total = int(total_raw or 0)
        except (TypeError, ValueError):
            total = 0
        if total < 0:
            total = 0
        role = _normalize_account_role(user.account_role)
        role_lit = cast(Literal["client", "manager", "admin"], role)
        out.append(
            UserListItem(
                id=user.id,
                registered_at=user.registered_at,
                email=user.email,
                account_role=role_lit,
                telegram_id=user.telegram_id,
                telegram_properties=user.telegram_properties,
                subscription_until=user.subscription_until,
                total_traffic_bytes=total,
                referral_link_id=user.referral_link_id,
                token=(user.token if show_secrets else None),
                vless_uuid=(user.vless_uuid if show_secrets else None),
            ),
        )
    return out


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(require_admin)],
    summary="Создать пользователя (токен подписки генерируется на сервере)",
)
async def create_user(
    body: UserCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    user = User(
        telegram_id=body.telegram_id,
        telegram_properties=body.telegram_properties,
        subscription_until=body.subscription_until,
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("create_user conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user


@router.post(
    "/extend-active-subscriptions",
    response_model=ExtendActiveSubscriptionsResponse,
    dependencies=[Depends(require_admin)],
    summary=(
        "Продлить подписку: прибавить дни всем с активной конечной подпиской "
        "(subscription_until задан и ≥ сегодня; бессрочные записи не меняются)"
    ),
)
async def extend_active_subscriptions(
    body: ExtendActiveSubscriptionsBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> ExtendActiveSubscriptionsResponse:
    days = body.days
    stmt = (
        update(User)
        .where(
            User.subscription_until.isnot(None),
            User.subscription_until >= date.today(),
        )
        .values(subscription_until=User.subscription_until + days)
    )
    result = session.execute(stmt)
    n = int(result.rowcount or 0)
    if n:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return ExtendActiveSubscriptionsResponse(updated_count=n)


@router.get(
    "/{user_id}/traffic-by-server",
    response_model=UserTrafficByServersBundle,
    dependencies=[Depends(require_admin)],
    summary="Трафик пользователя по всем узлам (из БД, накопленный Xray)",
)
async def user_traffic_by_server(
    user_id: int,
    session: ReadonlySessionDep,
) -> UserTrafficByServersBundle:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    stmt = (
        select(Server, UserServerTraffic)
        .outerjoin(
            UserServerTraffic,
            and_(
                UserServerTraffic.server_id == Server.id,
                UserServerTraffic.user_id == user_id,
            ),
        )
        .order_by(Server.id.asc())
    )
    rows = session.execute(stmt).all()
    out: list[UserTrafficPerServerRow] = []
    total_up = 0
    total_down = 0
    for server, ut in rows:
        up = int(ut.up_bytes or 0) if ut is not None else 0
        down = int(ut.down_bytes or 0) if ut is not None else 0
        total_up += up
        total_down += down
        out.append(
            UserTrafficPerServerRow(
                server_id=server.id,
                name=server.name,
                host=server.host,
                port=server.port,
                country=server.country or "",
                is_active=server.is_active,
                provision_ready=server.provision_ready,
                up_bytes=up,
                down_bytes=down,
                total_bytes=up + down,
            ),
        )
    return UserTrafficByServersBundle(
        user_id=user.id,
        telegram_id=user.telegram_id,
        subscription_until=user.subscription_until,
        servers=out,
        total_up_bytes=total_up,
        total_down_bytes=total_down,
    )


@router.delete(
    "/{user_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
    summary="Удалить пользователя; на узлах — синхронизация inbound без этого UUID",
)
async def delete_user(
    user_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    session.delete(user)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_admin)],
    summary="Обновить пользователя (подписка); после сохранения — синхронизация Xray на узлах",
)
async def patch_user(
    user_id: int,
    body: UserUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return user
    new_role = data.get("account_role")
    if new_role == "admin" and not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Нельзя назначить роль admin без пароля у пользователя",
        )
    for key, value in data.items():
        setattr(user, key, value)
    session.flush()
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user
