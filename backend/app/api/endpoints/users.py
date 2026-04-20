import logging
import uuid as uuid_lib
from secrets import token_urlsafe

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, require_admin
from app.core.config import settings
from app.core.queue import get_install_queue
from app.database.operations import table_insert
from app.models.user import User
from app.schemas.users import UserCreate, UserRead, UsersCountResponse, UserUpdate

log = logging.getLogger("app.users")

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)

_TOKEN_BYTES = 24


def _new_subscription_token() -> str:
    return token_urlsafe(_TOKEN_BYTES)


def _new_vless_uuid() -> str:
    return str(uuid_lib.uuid4())


def _enqueue_sync_xray_clients_all_servers() -> None:
    """После commit: поставить в RQ обновление inbound на всех provision_ready узлах."""
    try:
        q = get_install_queue()
        q.enqueue(
            "worker.jobs.sync_xray_clients_all_servers",
            job_timeout=max(settings.provision_job_timeout, 600),
        )
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь синхронизацию Xray (Redis недоступен)",
            exc_info=True,
        )


@router.get(
    "/count",
    response_model=UsersCountResponse,
    summary="Количество пользователей в БД",
)
async def users_count(session: SessionDep) -> UsersCountResponse:
    total = session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


@router.get(
    "",
    response_model=list[UserRead],
    summary="Список пользователей",
)
async def list_users(session: SessionDep) -> list[User]:
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
    token = _new_subscription_token()
    user = User(
        telegram_id=body.telegram_id,
        subscription_until=body.subscription_until,
        token=token,
        vless_uuid=_new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("create_user conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    background_tasks.add_task(_enqueue_sync_xray_clients_all_servers)
    return user


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
    background_tasks.add_task(_enqueue_sync_xray_clients_all_servers)
    return user
