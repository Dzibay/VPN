import logging
import uuid as uuid_lib
from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, get_current_user_dep
from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.queue import get_install_queue
from app.core.user_token import create_user_jwt
from app.database.operations import table_insert
from app.models.user import User
from app.schemas.account import AccountLoginBody, AccountMeResponse, AccountRegisterBody
from app.schemas.auth import TokenResponse

log = logging.getLogger("app.account")

router = APIRouter(prefix="/account", tags=["account"])

_TOKEN_BYTES = 24


def _new_subscription_token() -> str:
    return token_urlsafe(_TOKEN_BYTES)


def _new_vless_uuid() -> str:
    return str(uuid_lib.uuid4())


def _subscription_active(user: User) -> bool:
    from datetime import date

    if user.subscription_until is None:
        return True
    return user.subscription_until >= date.today()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _enqueue_sync_xray_clients_all_servers() -> None:
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


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Регистрация пользователя портала (email + пароль)",
)
async def register(
    body: AccountRegisterBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    email = _normalize_email(str(body.email))
    pwd_hash = hash_password(body.password)
    user = User(
        email=email,
        password_hash=pwd_hash,
        telegram_id=None,
        subscription_until=None,
        token=_new_subscription_token(),
        vless_uuid=_new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("register conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким email уже зарегистрирован",
        ) from e
    background_tasks.add_task(_enqueue_sync_xray_clients_all_servers)
    try:
        token = create_user_jwt(settings, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход пользователя портала",
)
async def login(body: AccountLoginBody, session: SessionDep) -> TokenResponse:
    email = _normalize_email(str(body.email))
    stmt = select(User).where(User.email == email).limit(1)
    user = session.scalars(stmt).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    try:
        token = create_user_jwt(settings, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=AccountMeResponse,
    summary="Текущий пользователь портала (Bearer user JWT)",
)
async def me(
    user: Annotated[User, Depends(get_current_user_dep)],
) -> AccountMeResponse:
    if not user.email:
        raise HTTPException(status_code=500, detail="У записи нет email")
    return AccountMeResponse(
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        subscription_until=user.subscription_until,
        subscription_active=_subscription_active(user),
        subscription_token=user.token,
    )
