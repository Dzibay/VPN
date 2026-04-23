import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
)
from app.core.access_token import create_access_token
from app.core.auth_env import (
    admin_email_normalized,
    admin_password_configured,
    normalize_email,
    password_matches_admin,
)
from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.database.operations import table_insert
from app.domain.subscription import user_has_active_subscription
from app.models.user import User
from app.schemas.account import (
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    TelegramAuthBody,
)
from app.schemas.auth import TokenResponse
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход (администратор из env или пользователь из БД)",
)
async def login(body: AccountLoginBody, session: ReadonlySessionDep) -> TokenResponse:
    email = normalize_email(str(body.email))
    if admin_password_configured(settings) and email == admin_email_normalized(settings):
        if not password_matches_admin(settings, body.password):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        try:
            token = create_access_token(settings, role="admin")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return TokenResponse(access_token=token, role="admin")

    stmt = select(User).where(User.email == email).limit(1)
    user = session.scalars(stmt).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    try:
        token = create_access_token(settings, role="user", user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token, role="user")


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
    email = normalize_email(str(body.email))
    if admin_password_configured(settings) and email == admin_email_normalized(settings):
        raise HTTPException(
            status_code=409,
            detail="Этот email зарезервирован для администратора",
        )
    pwd_hash = hash_password(body.password)
    user = User(
        email=email,
        password_hash=pwd_hash,
        telegram_id=None,
        subscription_until=None,
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("register conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким email уже зарегистрирован",
        ) from e
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    try:
        token = create_access_token(settings, role="user", user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token, role="user")


@router.post(
    "/telegram",
    response_model=TokenResponse,
    status_code=201,
    summary="Вход и регистрация через Telegram (секрет X-Telegram-Bot-Secret; вызывает бэкенд бота)",
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    x_telegram_bot_secret: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    expected = (settings.telegram_bot_api_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="TELEGRAM_BOT_API_SECRET не задан: эндпоинт отключён",
        )
    got = (x_telegram_bot_secret or "").strip()
    if not got or not secrets.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="Недействительный секрет бота")

    tid = body.telegram_id
    stmt = select(User).where(User.telegram_id == tid).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        user = User(
            email=None,
            password_hash=None,
            telegram_id=tid,
            subscription_until=None,
            token=new_subscription_token(),
            vless_uuid=new_vless_uuid(),
        )
        try:
            table_insert(session, user)
        except IntegrityError as e:
            log.warning("telegram register conflict, refetch: %s", e)
            session.rollback()
            user = session.scalars(
                select(User).where(User.telegram_id == tid).limit(1)
            ).first()
            if user is None:
                raise HTTPException(
                    status_code=409,
                    detail="Не удалось создать или найти пользователя по telegram_id",
                ) from e
        else:
            background_tasks.add_task(enqueue_sync_xray_clients_all_servers)

    try:
        token = create_access_token(settings, role="user", user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token, role="user")


@router.get(
    "/me",
    response_model=AccountMeResponse,
    summary="Профиль по Bearer JWT (после login/register): пользователь из БД или админ из env",
)
async def me(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> AccountMeResponse:
    if principal.role == "admin":
        return AccountMeResponse(
            role="admin",
            id=None,
            email=admin_email_normalized(settings),
            telegram_id=None,
            subscription_until=None,
            subscription_active=False,
            subscription_token="",
        )
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if not user.email and not user.telegram_id:
        raise HTTPException(
            status_code=500,
            detail="У записи нет ни email, ни telegram_id",
        )
    return AccountMeResponse(
        role="user",
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        subscription_token=user.token,
    )
