import logging
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_telegram_bot_api_secret,
)
from app.core.access_token import create_access_token
from app.core.auth_env import normalize_email
from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.database.operations import table_insert
from app.domain.subscription import (
    subscription_until_after_registration,
    user_has_active_subscription,
)
from app.domain.user_traffic import user_traffic_totals
from app.models.referral_link import ReferralLink
from app.models.user import User
from app.schemas.account import (
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    TelegramAuthBody,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
    telegram_auth_has_profile_fields,
)
from app.schemas.auth import TokenResponse
from app.services.referral_link_service import increment_referral_counter
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.auth")


def _jwt_role_for_user(user: User) -> Literal["user", "manager", "admin"]:
    """JWT-роль по users.account_role (client → user)."""
    ar = getattr(user, "account_role", None) or "client"
    if ar == "admin":
        return "admin"
    if ar == "manager":
        return "manager"
    return "user"


# Примеры ответа GET /api/auth/me в OpenAPI (ключи с null в JSON стандарте часто не показывают).
_AUTH_ME_OPENAPI_EXAMPLES: dict = {
    "user_with_email": {
        "summary": "Пользователь: email, Telegram, подписка",
        "description": "Типичный случай после веб-регистрации с привязкой Telegram.",
        "value": {
            "role": "user",
            "id": 42,
            "email": "user@example.com",
            "telegram_id": 123456789,
            "telegram_properties": {
                "username": "ivan_dev",
                "first_name": "Ivan",
                "last_name": "Petrov",
                "topic_id": 2,
            },
            "subscription_until": "2026-12-31",
            "subscription_active": True,
            "subscription_token": "subscription-token-example",
            "subscription_open_clients": [
                {
                    "client_code": "happ",
                    "display_name": "Happ",
                    "store_platforms": ["android", "ios", "windows", "macos", "linux"],
                },
            ],
            "traffic_up_bytes": 1073741824,
            "traffic_down_bytes": 5368709120,
            "traffic_total_bytes": 6442450944,
            "registered_at": "2026-03-01T10:30:00+00:00",
        },
    },
    "user_telegram_only": {
        "summary": "Только Telegram: email/срок подписки часто null",
        "value": {
            "role": "user",
            "id": 7,
            "telegram_id": 998877665,
            "telegram_properties": {
                "username": "daria_vpn",
                "first_name": "Daria",
            },
            "subscription_active": False,
            "subscription_token": "subscription-token-telegram",
            "subscription_open_clients": [],
        },
    },
    "admin": {
        "summary": "Админ (users.account_role = admin)",
        "description": (
            "id, telegram_id, telegram_properties, subscription_until в ответе — null; "
            "subscription_token — пустая строка. Эти поля в примере опущены (см. схему)."
        ),
        "value": {
            "role": "admin",
            "email": "admin@example.com",
            "registered_at": "2025-01-15T08:00:00+00:00",
            "subscription_active": False,
            "subscription_token": "",
        },
    },
}

router = APIRouter(prefix="/auth")


@router.post(
    "/login",
    response_model=TokenResponse,
    tags=["public"],
    summary="Вход по email и паролю (учётная запись в БД)",
)
async def login(body: AccountLoginBody, session: ReadonlySessionDep) -> TokenResponse:
    email = normalize_email(str(body.email))
    stmt = select(User).where(User.email == email).limit(1)
    user = session.scalars(stmt).first()

    if user is not None:
        if not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        jwt_role = _jwt_role_for_user(user)
        try:
            token = create_access_token(settings, role=jwt_role, user_id=user.id)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return TokenResponse(access_token=token, role=jwt_role)

    raise HTTPException(status_code=401, detail="Неверный email или пароль")


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    tags=["public"],
    summary="Регистрация пользователя портала (email + пароль)",
)
async def register(
    body: AccountRegisterBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    email = normalize_email(str(body.email))
    pwd_hash = hash_password(body.password)
    user = User(
        email=email,
        password_hash=pwd_hash,
        telegram_id=None,
        telegram_properties=None,
        subscription_until=subscription_until_after_registration(),
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

    if body.referral_token:
        rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
        rlink = session.scalars(rstmt).first()
        if rlink is not None:
            user.referral_link_id = rlink.id
            increment_referral_counter(session, rlink.id, "registrations")
            session.flush()

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
    tags=["public"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Вход и регистрация через Telegram (секрет X-Telegram-Bot-Secret; вызывает бэкенд бота)",
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    tid = body.telegram_id
    profile = merge_telegram_auth_profile(body, None)
    stmt = select(User).where(User.telegram_id == tid).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        user = User(
            email=None,
            password_hash=None,
            telegram_id=tid,
            telegram_properties=profile,
            subscription_until=subscription_until_after_registration(),
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
            if body.referral_token:
                rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
                rlink = session.scalars(rstmt).first()
                if rlink is not None:
                    user.referral_link_id = rlink.id
                    increment_referral_counter(session, rlink.id, "registrations")
                    session.flush()
            background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    elif telegram_auth_has_profile_fields(body):
        user.telegram_properties = merge_telegram_auth_profile(
            body,
            user.telegram_properties,
        )
        session.flush()

    try:
        jwt_role = _jwt_role_for_user(user)
        token = create_access_token(settings, role=jwt_role, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token, role=jwt_role)


@router.get(
    "/me",
    response_model=AccountMeResponse,
    tags=["user"],
    summary="Профиль по Bearer JWT (учётная запись в БД)",
    responses={
        200: {
            "description": "Профиль",
            "content": {
                "application/json": {
                    "examples": _AUTH_ME_OPENAPI_EXAMPLES,
                }
            },
        }
    },
)
async def me(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> AccountMeResponse:
    if principal.role == "admin":
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="Недействительный токен")
        user = session.get(User, principal.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        if user.account_role != "admin":
            raise HTTPException(status_code=401, detail="Недействительный токен")
        up_b, down_b, total_b = user_traffic_totals(session, user.id)
        return AccountMeResponse(
            role="admin",
            id=user.id,
            email=user.email,
            telegram_id=user.telegram_id,
            telegram_properties=user.telegram_properties,
            registered_at=user.registered_at,
            subscription_until=user.subscription_until,
            subscription_active=user_has_active_subscription(user),
            subscription_token=user.token,
            subscription_open_clients=build_subscription_open_client_items(),
            traffic_up_bytes=up_b,
            traffic_down_bytes=down_b,
            traffic_total_bytes=total_b,
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
    up_b, down_b, total_b = user_traffic_totals(session, user.id)
    api_role = "manager" if principal.role == "manager" else "user"
    return AccountMeResponse(
        role=api_role,
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        telegram_properties=user.telegram_properties,
        registered_at=user.registered_at,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        subscription_token=user.token,
        subscription_open_clients=build_subscription_open_client_items(),
        traffic_up_bytes=up_b,
        traffic_down_bytes=down_b,
        traffic_total_bytes=total_b,
    )
