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
from app.core.request_subject import bind_request_subject_user
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
    RegisterAuthResponse,
    SubscriptionConnectionItem,
    TokenResponse,
    build_subscription_open_client_items,
)
from app.domain.services.email_verification_service import (
    complete_email_registration_flow,
    require_verified_email_for_login,
)
from app.domain.public_urls import (
    support_telegram_public_url,
    telegram_bot_public_page_url,
)
from app.domain.referrals.registration_tasks import create_notify_ref_reg_task_if_applicable
from app.domain.referrals.repository import increment_referral_counter
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.subscription.devices import (
    effective_subscription_device_limit,
    list_subscription_connection_records,
)
from app.domain.subscription.traffic_limit import apply_default_traffic_limit_for_new_client
from app.domain.subscription.validity import (
    subscription_until_after_registration,
    trial_extra_days_for_referral_link,
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
    require_verified_email_for_login(user)
    jwt_role = jwt_role_for_user(user)
    token = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
    bind_request_subject_user(int(user.id), source="login_password")
    return TokenResponse(access_token=token, role=jwt_role)


async def register_with_email(
    session: AsyncSession,
    body: AccountRegisterBody,
    cfg: Settings,
    redis_conn: object,
) -> RegisterAuthResponse:
    """Регистрация по email и паролю; ответ — JWT или запрос подтверждения почты.

    При наличии валидного ``referral_token`` инкремент счётчика регистраций по реферальной
    ссылке делается в той же транзакции, что и вставка пользователя. Если ссылка с
    ``owner_kind=user``, к базовому триалу добавляются дни из
    ``TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION``.
    """
    email = normalize_email(str(body.email))
    pwd_hash = await run_in_threadpool(hash_password, body.password)
    rlink: ReferralLink | None = None
    if body.referral_token:
        rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
        rlink = (await session.scalars(rstmt)).first()
    trial_extra = trial_extra_days_for_referral_link(rlink)
    user = User(
        email=email,
        password_hash=pwd_hash,
        telegram_id=None,
        telegram_properties=None,
        account_role="client",
        subscription_until=subscription_until_after_registration(extra_trial_days=trial_extra),
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    apply_default_traffic_limit_for_new_client(user, cfg=cfg)
    try:
        await table_insert(session, user)
    except IntegrityError as e:
        log.warning("register conflict: %s", e)
        raise ConflictError("Пользователь с таким email уже зарегистрирован") from e

    if rlink is not None:
        user.referral_link_id = rlink.id
        await increment_referral_counter(session, rlink.id, "registrations")
        await session.flush()
        await create_notify_ref_reg_task_if_applicable(
            session,
            referral_link=rlink,
            referee_user_id=int(user.id),
        )

    result = await complete_email_registration_flow(
        session,
        user,
        cfg,
        redis_conn,
        bind_source="register_email",
    )
    if isinstance(result, TokenResponse):
        return RegisterAuthResponse.from_token(result)
    return RegisterAuthResponse.from_pending(result)


async def account_me_from_user(
    session: AsyncSession,
    user: User,
    cfg: Settings,
    *,
    api_role: str | None = None,
) -> AccountMeResponse:
    """Сборка ответа профиля по строке пользователя (роль из JWT или из ``jwt_role_for_user``)."""
    role = api_role if api_role is not None else jwt_role_for_user(user)
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
        support_telegram_url=support_telegram_public_url(cfg),
        registered_at=user.registered_at,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user, used_bytes=total_b),
        subscription_token=user.token,
        subscription_open_clients=build_subscription_open_client_items(),
        subscription_connections_count=len(subs_conns),
        subscription_connections_limit=subs_dev_limit,
        subscription_connections=subs_conns,
        traffic_up_bytes=up_b,
        traffic_down_bytes=down_b,
        traffic_total_bytes=total_b,
        traffic_limit_bytes=(
            int(user.traffic_limit_bytes) if user.traffic_limit_bytes is not None else None
        ),
        has_site_password=bool(user.password_hash),
    )


async def account_me(
    session: AsyncSession, principal: BearerPrincipal, cfg: Settings,
) -> AccountMeResponse:
    """Профиль текущего пользователя по JWT (включая трафик и активные подписочные устройства)."""
    user, role = await resolve_authenticated_user(session, principal)
    return await account_me_from_user(session, user, cfg, api_role=role)


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
