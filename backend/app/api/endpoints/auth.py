import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.config import settings
from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    require_telegram_bot_api_secret,
)
from app.domain.models.auth import (
    AccountLoginBody,
    AccountRegisterBody,
    TelegramAuthBody,
    TelegramAuthUserResponse,
    TelegramSiteLinkCompleteBody,
    TelegramSiteLinkPreviewResponse,
    TokenResponse,
)
from app.domain.services.auth_service import login_with_password, register_with_email
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
    response_model=TokenResponse,
    status_code=201,
    tags=["public"],
    summary="Регистрация по email и паролю; ответ содержит JWT",
)
async def register(
    body: AccountRegisterBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    resp = await register_with_email(session, body, settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/telegram",
    response_model=TelegramAuthUserResponse,
    status_code=201,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary=(
        "Аутентификация и регистрация через Telegram; ответ — профиль пользователя"
    ),
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramAuthUserResponse:
    resp = await telegram_authenticate(session, body, settings)
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
    response_model=TokenResponse,
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
) -> TokenResponse:
    resp = await telegram_site_link_complete(session, body, get_redis(), settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp
