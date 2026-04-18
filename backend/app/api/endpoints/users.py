import logging
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, require_admin
from app.database.operations import table_insert
from app.models.user import User
from app.schemas.users import UserCreate, UserRead, UsersCountResponse

log = logging.getLogger("app.users")

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)

_TOKEN_BYTES = 24


def _new_subscription_token() -> str:
    return token_urlsafe(_TOKEN_BYTES)


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
async def create_user(body: UserCreate, session: SessionDep) -> User:
    token = _new_subscription_token()
    user = User(
        telegram_id=body.telegram_id,
        subscription_until=body.subscription_until,
        token=token,
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("create_user conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    return user
