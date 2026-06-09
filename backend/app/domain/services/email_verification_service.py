"""Подтверждение email: токены в Redis, письма SMTP, проверка при входе."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.auth_env import normalize_email
from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.request_subject import bind_request_subject_user
from app.core.time import utc_now
from app.domain.auth.email_verify_tokens import (
    EmailVerifyRedisError,
    delete_email_verify_token,
    resolve_email_verify_user_id,
    store_email_verify_token,
)
from app.domain.auth.jwt import issue_access_token_or_http_error, jwt_role_for_user
from app.domain.models.auth import (
    EmailResendVerificationBody,
    EmailVerificationPendingResponse,
    TokenResponse,
)
from app.domain.public_urls import public_spa_base_url
from app.infrastructure.email.smtp_sender import (
    SmtpDeliveryError,
    send_verification_email_sync,
    smtp_configured,
)
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.email_verification")

EMAIL_NOT_VERIFIED_CODE = "email_not_verified"


def user_has_verified_email(user: User) -> bool:
    mail = (user.email or "").strip()
    if not mail:
        return True
    return user.email_verified_at is not None


def email_verification_enabled(cfg: Settings) -> bool:
    return smtp_configured(cfg) or not cfg.debug


def require_verified_email_for_login(user: User) -> None:
    if user_has_verified_email(user):
        return
    raise ForbiddenError(
        {
            "code": EMAIL_NOT_VERIFIED_CODE,
            "message": (
                "Подтвердите email по ссылке из письма. "
                "Если письмо не пришло — запросите повторную отправку."
            ),
        },
    )


def _verification_url(cfg: Settings, token: str) -> str:
    base = public_spa_base_url(cfg)
    if not base:
        raise ServiceUnavailableError(
            "Не задан публичный URL SPA: задайте SITE_ADDRESS в окружении.",
        )
    return f"{base}/verify-email?token={quote(token, safe='')}"


async def mark_email_verified_now(session: AsyncSession, user: User) -> None:
    user.email_verified_at = utc_now()
    await session.flush()


async def issue_token_for_verified_user(user: User, cfg: Settings) -> TokenResponse:
    jwt_role = jwt_role_for_user(user)
    access = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
    return TokenResponse(access_token=access, role=jwt_role)


async def _send_verification_email_now(
    cfg: Settings,
    *,
    to_email: str,
    verify_url: str,
) -> None:
    try:
        await run_in_threadpool(
            send_verification_email_sync,
            cfg,
            to_email=to_email,
            verify_url=verify_url,
        )
    except SmtpDeliveryError as e:
        log.warning("verification email failed for %s: %s", to_email, e)
        raise ServiceUnavailableError(str(e)) from e
    except Exception:
        log.exception("verification email failed for %s", to_email)
        raise ServiceUnavailableError(
            "Не удалось отправить письмо подтверждения. Попробуйте позже или обратитесь в поддержку.",
        ) from None


async def complete_email_registration_flow(
    session: AsyncSession,
    user: User,
    cfg: Settings,
    redis_conn: object,
    *,
    bind_source: str,
) -> TokenResponse | EmailVerificationPendingResponse:
    """После сохранения email: авто-подтверждение в DEBUG без SMTP или письмо с ссылкой."""
    mail = (user.email or "").strip()
    if not mail:
        raise BadRequestError("У пользователя не задан email")

    if not email_verification_enabled(cfg):
        await mark_email_verified_now(session, user)
        bind_request_subject_user(int(user.id), source=bind_source)
        return await issue_token_for_verified_user(user, cfg)

    if not smtp_configured(cfg):
        raise ServiceUnavailableError(
            "Подтверждение email включено, но SMTP не настроен (задайте SMTP_HOST и др.).",
        )

    try:
        token = store_email_verify_token(
            redis_conn,
            int(user.id),
            ttl_sec=int(cfg.email_verification_ttl_sec),
        )
    except EmailVerifyRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None

    verify_url = _verification_url(cfg, token)
    await _send_verification_email_now(cfg, to_email=mail, verify_url=verify_url)
    bind_request_subject_user(int(user.id), source=f"{bind_source}_pending")
    return EmailVerificationPendingResponse(email=mail)


async def schedule_verification_email(
    user: User,
    cfg: Settings,
    redis_conn: object,
) -> EmailVerificationPendingResponse:
    mail = (user.email or "").strip()
    if not mail:
        raise BadRequestError("У пользователя не задан email")

    if not smtp_configured(cfg):
        raise ServiceUnavailableError("SMTP не настроен")

    try:
        token = store_email_verify_token(
            redis_conn,
            int(user.id),
            ttl_sec=int(cfg.email_verification_ttl_sec),
        )
    except EmailVerifyRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None

    verify_url = _verification_url(cfg, token)
    await _send_verification_email_now(cfg, to_email=mail, verify_url=verify_url)
    return EmailVerificationPendingResponse(email=mail)


async def verify_email_by_token(
    session: AsyncSession,
    raw_token: str,
    redis_conn: object,
    cfg: Settings,
) -> TokenResponse:
    token = (raw_token or "").strip()
    if not token:
        raise BadRequestError("Не указан token")

    try:
        uid = resolve_email_verify_user_id(redis_conn, token)
    except EmailVerifyRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None
    if uid is None:
        raise NotFoundError("Ссылка недействительна или истекла")

    user = await session.get(User, uid)
    if user is None:
        raise NotFoundError("Пользователь не найден")

    if not user_has_verified_email(user):
        await mark_email_verified_now(session, user)

    try:
        delete_email_verify_token(redis_conn, token, int(user.id))
    except EmailVerifyRedisError:
        log.warning("verify-email: не удалось удалить токен из Redis")

    jwt_role = jwt_role_for_user(user)
    access = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
    bind_request_subject_user(int(user.id), source="verify_email")
    return TokenResponse(access_token=access, role=jwt_role)


async def resend_verification_email(
    session: AsyncSession,
    body: EmailResendVerificationBody,
    redis_conn: object,
    cfg: Settings,
) -> EmailVerificationPendingResponse:
    email = normalize_email(str(body.email))
    user = (
        await session.scalars(select(User).where(User.email == email).limit(1))
    ).first()
    if user is None or not user.password_hash:
        return EmailVerificationPendingResponse(
            email=body.email,
            message=(
                "Если аккаунт с этим email существует и ожидает подтверждения, "
                "письмо будет отправлено."
            ),
        )
    if user_has_verified_email(user):
        return EmailVerificationPendingResponse(
            email=body.email,
            message="Если аккаунт с этим email существует, письмо будет отправлено.",
        )
    return await schedule_verification_email(user, cfg, redis_conn)
