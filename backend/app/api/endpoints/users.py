import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import ReadonlySessionDep, SessionDep, require_admin
from app.database.operations import table_insert
from app.models.server import Server
from app.models.user import User
from app.models.user_server_traffic import UserServerTraffic
from app.schemas.server_traffic import UserTrafficByServersBundle, UserTrafficPerServerRow
from app.schemas.users import UserCreate, UserRead, UsersCountResponse, UserUpdate
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.users")

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/count",
    response_model=UsersCountResponse,
    summary="Количество пользователей в БД",
)
async def users_count(session: ReadonlySessionDep) -> UsersCountResponse:
    total = session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


@router.get(
    "",
    response_model=list[UserRead],
    summary="Список пользователей",
)
async def list_users(session: ReadonlySessionDep) -> list[User]:
    stmt = select(User).order_by(User.id.desc())
    return list(session.scalars(stmt).all())


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    summary="Создать пользователя (токен подписки генерируется на сервере)",
)
async def create_user(
    body: UserCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    user = User(
        telegram_id=body.telegram_id,
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


@router.get(
    "/{user_id}/traffic-by-server",
    response_model=UserTrafficByServersBundle,
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
    for key, value in data.items():
        setattr(user, key, value)
    session.flush()
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user
