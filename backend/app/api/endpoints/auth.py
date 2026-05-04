import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app.config import settings
from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_telegram_bot_api_secret,
)
from app.domain.models.auth import (
    AccountChangePasswordBody,
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    TelegramAuthBody,
    TelegramAuthTokenResponse,
    TelegramSiteLinkCompleteBody,
    TelegramSiteLinkPreviewResponse,
    TelegramSiteLinkStartBody,
    TelegramSiteLinkStartResponse,
    TelegramSyncStartResponse,
    TelegramWebLinkBody,
    TelegramWebLinkResponse,
    TokenResponse,
)
from app.domain.services.auth_service import (
    account_me,
    change_account_password,
    login_with_password,
    register_with_email,
)
from app.domain.services.telegram_auth_service import (
    telegram_authenticate,
    telegram_link_web_account,
    telegram_site_link_complete,
    telegram_site_link_preview_response,
    telegram_site_link_start,
    telegram_sync_start_link,
)
from app.domain.users.xray_sync_queue import enqueue_sync_xray_clients_all_servers
from app.infrastructure.cache import get_redis

log = logging.getLogger("app.auth")

_AUTH_ME_OPENAPI_EXAMPLES: dict = {
    "user_with_email": {
        "summary": "Клиентская учётная запись (email и Telegram)",
        "description": "Типичный ответ после регистрации на сайте и привязки Telegram.",
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
            "subscription_connections_count": 2,
            "subscription_connections_limit": None,
            "subscription_connections": [
                {"id": 1, "os": "Windows", "user_agent": "Happ/2.9.1/Windows/example"},
                {"id": 2, "os": "Windows", "user_agent": "v2raytun/windows"},
            ],
            "traffic_up_bytes": 1073741824,
            "traffic_down_bytes": 5368709120,
            "traffic_total_bytes": 6442450944,
            "registered_at": "2026-03-01T10:30:00+00:00",
            "has_site_password": True,
        },
    },
    "user_telegram_only": {
        "summary": "Учётная запись только через Telegram",
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
            "has_site_password": False,
        },
    },
    "admin": {
        "summary": "Администратор",
        "description": "Часть полей отсутствует или равна null; полный перечень см. в схеме ответа.",
        "value": {
            "role": "admin",
            "email": "admin@example.com",
            "registered_at": "2025-01-15T08:00:00+00:00",
            "subscription_active": False,
            "subscription_token": "",
            "has_site_password": True,
        },
    },
}

router = APIRouter(prefix="/auth")


@router.post(
    "/login",
    response_model=TokenResponse,
    tags=["public"],
    summary="Аутентификация по email и паролю; ответ содержит JWT",
)
async def login(body: AccountLoginBody, session: ReadonlySessionDep) -> TokenResponse:
    return login_with_password(session, body, settings)


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
    resp = register_with_email(session, body, settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/telegram",
    response_model=TelegramAuthTokenResponse,
    status_code=201,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Аутентификация и регистрация через Telegram (обязательный заголовок X-Telegram-Bot-Secret)",
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramAuthTokenResponse:
    resp = telegram_authenticate(session, body, settings)
    if resp.is_new_user:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/telegram/link",
    response_model=TelegramWebLinkResponse,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Привязка Telegram к учётной записи по одноразовому токену из личного кабинета",
)
async def telegram_link_web_account_ep(
    body: TelegramWebLinkBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramWebLinkResponse:
    resp = telegram_link_web_account(session, body, get_redis(), settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/telegram/site-link/start",
    response_model=TelegramSiteLinkStartResponse,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Ссылка на сайт: форма привязки email/пароля или вход в кабинет по JWT (поля site_url и has_account)",
)
async def telegram_site_link_start_ep(
    body: TelegramSiteLinkStartBody,
    session: ReadonlySessionDep,
) -> TelegramSiteLinkStartResponse:
    return telegram_site_link_start(session, body, get_redis(), settings)


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
    return telegram_site_link_preview_response(session, get_redis(), token, settings)


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
    resp = telegram_site_link_complete(session, body, get_redis(), settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/me/telegram-sync-start",
    response_model=TelegramSyncStartResponse,
    tags=["user"],
    summary="Одноразовая deep link-ссылка на бота (t.me/…?start=…) для привязки Telegram",
)
async def telegram_sync_start(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> TelegramSyncStartResponse:
    return telegram_sync_start_link(session, principal, get_redis(), settings)


@router.get(
    "/me",
    response_model=AccountMeResponse,
    tags=["user"],
    summary="Профиль текущего пользователя по JWT",
    responses={
        200: {
            "description": "Данные учётной записи",
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
    return account_me(session, principal, settings)


@router.post(
    "/me/change-password",
    status_code=204,
    tags=["user"],
    summary="Смена пароля: текущий и новый (JWT)",
)
async def change_password(
    body: AccountChangePasswordBody,
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> Response:
    change_account_password(session, principal, body)
    return Response(status_code=204)
