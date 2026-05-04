"""Аутентификация по email/паролю и операции личного кабинета.

Telegram-сценарии (login по telegram_id, привязка/слияние) живут в
:mod:`app.domain.services.telegram_auth_service`, низкоуровневые примитивы — в
:mod:`app.domain.auth`.
"""

from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.auth_env import normalize_email
from app.core.dependencies import BearerPrincipal
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, UnauthorizedError
from app.core.passwords import hash_password, verify_password
from app.domain.auth.jwt import issue_access_token_or_http_error, jwt_role_for_user
from app.domain.auth.permissions import resolve_authenticated_user
from app.domain.models.auth import (
    AccountChangePasswordBody,
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    SubscriptionConnectionItem,
    TokenResponse,
    build_subscription_open_client_items,
)
from app.domain.public_urls import telegram_bot_public_page_url
from app.domain.referrals.repository import increment_referral_counter
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.subscription.devices import (
    effective_subscription_device_limit,
    list_subscription_connection_records,
)
from app.domain.subscription.validity import (
    subscription_until_after_registration,
    user_has_active_subscription,
)
from app.domain.user_traffic import user_traffic_totals
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.auth_service")


async def login_with_password(
    session: AsyncSession, body: AccountLoginBody, cfg: Settings,
) -> TokenResponse:
    """Логин по email и паролю; ответ — JWT-токен с API-ролью."""
    email = normalize_email(str(body.email))
    user = (
        await session.scalars(select(User).where(User.email == email).limit(1))
    ).first()
    if user is None:
        raise UnauthorizedError("Неверный email или пароль")
    if not user.password_hash:
        raise UnauthorizedError("Неверный email или пароль")
    # bcrypt — CPU-bound (~100–300 мс): держим за пределами event loop.
    ok = await run_in_threadpool(verify_password, body.password, user.password_hash)
    if not ok:
        raise UnauthorizedError("Неверный email или пароль")
    jwt_role = jwt_role_for_user(user)
    token = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
    return TokenResponse(access_token=token, role=jwt_role)


async def register_with_email(
    session: AsyncSession, body: AccountRegisterBody, cfg: Settings,
) -> TokenResponse:
    """Регистрация по email и паролю; ответ — JWT-токен.

    При наличии валидного ``referral_token`` инкремент счётчика регистраций по реферальной
    ссылке делается в той же транзакции, что и вставка пользователя.
    """
    email = normalize_email(str(body.email))
    pwd_hash = await run_in_threadpool(hash_password, body.password)
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
        await table_insert(session, user)
    except IntegrityError as e:
        log.warning("register conflict: %s", e)
        raise ConflictError("Пользователь с таким email уже зарегистрирован") from e

    if body.referral_token:
        rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
        rlink = (await session.scalars(rstmt)).first()
        if rlink is not None:
            user.referral_link_id = rlink.id
            await increment_referral_counter(session, rlink.id, "registrations")
            await session.flush()

    token = issue_access_token_or_http_error(cfg, role="user", user_id=user.id)
    return TokenResponse(access_token=token, role="user")


async def account_me(
    session: AsyncSession, principal: BearerPrincipal, cfg: Settings,
) -> AccountMeResponse:
    """Профиль текущего пользователя по JWT (включая трафик и активные подписочные устройства)."""
    user, role = await resolve_authenticated_user(session, principal)

    up_b, down_b, total_b = await user_traffic_totals(session, user.id)
    raw_conns = await list_subscription_connection_records(session, user.id)
    subs_dev_limit = effective_subscription_device_limit(cfg)
    subs_conns = [SubscriptionConnectionItem(**r) for r in raw_conns]

    return AccountMeResponse(
        role=role,
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        telegram_properties=user.telegram_properties,
        telegram_bot_page_url=telegram_bot_public_page_url(cfg),
        registered_at=user.registered_at,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        subscription_token=user.token,
        subscription_open_clients=build_subscription_open_client_items(),
        subscription_connections_count=len(subs_conns),
        subscription_connections_limit=subs_dev_limit,
        subscription_connections=subs_conns,
        traffic_up_bytes=up_b,
        traffic_down_bytes=down_b,
        traffic_total_bytes=total_b,
        has_site_password=bool(user.password_hash),
    )


async def change_account_password(
    session: AsyncSession,
    principal: BearerPrincipal,
    body: AccountChangePasswordBody,
) -> None:
    """Смена пароля для аккаунта с email; верифицирует текущий и запрещает совпадение с новым."""
    user, _ = await resolve_authenticated_user(session, principal)
    if not user.password_hash:
        raise BadRequestError(
            "Для этого аккаунта не задан пароль входа на сайте. "
            "Задайте пароль при регистрации или через привязку email в боте.",
        )
    cur_ok = await run_in_threadpool(verify_password, body.current_password, user.password_hash)
    if not cur_ok:
        raise ForbiddenError("Неверный текущий пароль")
    if len(body.new_password.encode("utf-8")) > 72:
        raise BadRequestError("Пароль слишком длинный (не более 72 байт в UTF-8)")
    same = await run_in_threadpool(verify_password, body.new_password, user.password_hash)
    if same:
        raise BadRequestError("Новый пароль совпадает с текущим")
    user.password_hash = await run_in_threadpool(hash_password, body.new_password)
    await session.flush()
