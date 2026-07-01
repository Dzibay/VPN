import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.config import settings
from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    require_telegram_bot_api_secret,
)
from app.domain.tenant.project_context import ProjectContext
from app.domain.models.auth import (
    AccountLoginBody,
    AccountRegisterBody,
    EmailResendVerificationBody,
    EmailVerificationPendingResponse,
    RegisterAuthResponse,
    TelegramAuthBody,
    TelegramAuthUserResponse,
    TelegramSiteLinkCompleteBody,
    TelegramSiteLinkPreviewResponse,
    TokenResponse,
)
from app.domain.services.auth_service import login_with_password, register_with_email
from app.domain.services.email_verification_service import (
    resend_verification_email,
    verify_email_by_token,
)
from app.domain.services.telegram_auth_service import (
    telegram_authenticate,
    telegram_site_link_complete,
    telegram_site_link_preview_response,
)
from app.domain.users.xray_sync_queue import enqueue_sync_xray_clients_all_servers
from app.infrastructure.cache import get_redis

log = logging.getLogger("app.auth")

router = APIRouter(prefix="/auth")


@router.post(
    "/login",
    response_model=TokenResponse,
    tags=["public"],
    summary="Аутентификация по email и паролю; ответ содержит JWT",
)
async def login(body: AccountLoginBody, session: ReadonlySessionDep) -> TokenResponse:
    return await login_with_password(session, body, settings)


@router.post(
    "/register",
    response_model=RegisterAuthResponse,
    status_code=201,
    tags=["public"],
    summary="Регистрация по email и паролю; JWT или ожидание подтверждения почты",
)
async def register(
    body: AccountRegisterBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> RegisterAuthResponse:
    resp = await register_with_email(session, body, settings, get_redis())
    if resp.status == "ok":
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.get(
    "/verify-email",
    response_model=TokenResponse,
    tags=["public"],
    summary="Подтверждение email по одноразовой ссылке из письма; ответ — JWT",
)
async def verify_email_ep(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    token: str = Query(..., min_length=1, max_length=96, description="Токен из письма"),
) -> TokenResponse:
    resp = await verify_email_by_token(session, token, get_redis(), settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/resend-verification",
    response_model=EmailVerificationPendingResponse,
    tags=["public"],
    summary="Повторная отправка письма подтверждения email",
)
async def resend_verification_ep(
    body: EmailResendVerificationBody,
    session: SessionDep,
) -> EmailVerificationPendingResponse:
    return await resend_verification_email(session, body, get_redis(), settings)


@router.post(
    "/telegram",
    response_model=TelegramAuthUserResponse,
    status_code=201,
    tags=["telegram"],
    summary=(
        "Аутентификация и регистрация через Telegram; ответ — профиль пользователя"
    ),
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    project: Annotated[ProjectContext, Depends(require_telegram_bot_api_secret)],
) -> TelegramAuthUserResponse:
    resp = await telegram_authenticate(session, body, settings, project=project)
    if resp.is_new_user:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.get(
    "/telegram/site-link/preview",
    response_model=TelegramSiteLinkPreviewResponse,
    tags=["public"],
    summary="Данные Telegram по одноразовому token из URL (до отправки формы)",
)
async def telegram_site_link_preview_ep(
    session: ReadonlySessionDep,
    token: str = Query(
        ...,
        min_length=1,
        max_length=96,
        description="Параметр token из URL",
    ),
) -> TelegramSiteLinkPreviewResponse:
    return await telegram_site_link_preview_response(session, get_redis(), token, settings)


@router.post(
    "/telegram/site-link/complete",
    response_model=RegisterAuthResponse,
    tags=["public"],
    summary=(
        "По одноразовому token: новый email на Telegram-аккаунт либо объединение с "
        "существующим email при верном пароле"
    ),
)
async def telegram_site_link_complete_ep(
    body: TelegramSiteLinkCompleteBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> RegisterAuthResponse:
    resp = await telegram_site_link_complete(session, body, get_redis(), settings)
    if resp.status == "ok":
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp
