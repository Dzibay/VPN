"""Эндпоинты профиля по JWT: GET/POST /api/me/..."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.config import settings
from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_roles,
)
from app.core.exceptions import ForbiddenError
from app.domain.models.auth import (
    AccountChangePasswordBody,
    AccountMeResponse,
    TelegramSyncStartResponse,
)
from app.domain.models.payments import (
    SitePaymentTariffsResponse,
    UserPaymentsListResponse,
    YookassaCheckoutBody,
    YookassaCheckoutResponse,
)
from app.domain.models.support_messages import (
    SupportMessageCreate,
    SupportMessageRead,
    SupportMessagesListResponse,
    SupportUnreadCountResponse,
)
from app.domain.services.auth_service import account_me, change_account_password
from app.domain.services.me_service import delete_subscription_device, list_my_payments
from app.domain.services.support_messages_service import (
    count_unread_support_for_user,
    create_user_support_message,
    list_my_support_messages,
    mark_support_seen_for_user,
)
from app.domain.services.telegram_auth_service import telegram_sync_start_link
from app.domain.services.yookassa_service import (
    create_yookassa_checkout,
    yookassa_tariffs_public_response,
)
from app.infrastructure.cache import get_redis

router = APIRouter(prefix="/me", tags=["user"])

require_cabinet_jwt = require_roles("user", "admin", "manager")

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
            "traffic_limit_bytes": None,
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
            "traffic_total_bytes": 0,
            "traffic_limit_bytes": 21474836480,
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


@router.get(
    "",
    response_model=AccountMeResponse,
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
    return await account_me(session, principal, settings)


def _require_cabinet_user(principal: BearerPrincipal) -> None:
    if principal.user_id is None:
        raise ForbiddenError(detail="Требуется вход")


@router.get(
    "/payments",
    response_model=UserPaymentsListResponse,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="История оплат текущего пользователя",
)
async def me_payments_history(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    limit: int = Query(20, ge=1, le=100, description="Размер страницы"),
    offset: int = Query(0, ge=0, description="Смещение"),
) -> UserPaymentsListResponse:
    _require_cabinet_user(principal)
    items, total = await list_my_payments(
        session,
        user_id=int(principal.user_id),
        limit=limit,
        offset=offset,
    )
    return UserPaymentsListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/payments/tariffs",
    response_model=SitePaymentTariffsResponse,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="Тарифы разовой оплаты (app/data/yookassa_tariffs.json)",
)
async def me_payment_tariffs(
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> SitePaymentTariffsResponse:
    _require_cabinet_user(principal)
    return yookassa_tariffs_public_response()


@router.post(
    "/payments/yookassa/checkout",
    response_model=YookassaCheckoutResponse,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="Создать платёж ЮKassa и получить URL для оплаты",
)
async def me_yookassa_checkout(
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    body: YookassaCheckoutBody,
) -> YookassaCheckoutResponse:
    _require_cabinet_user(principal)
    return await create_yookassa_checkout(
        settings,
        user_id=int(principal.user_id),
        months=int(body.months),
    )


@router.post(
    "/telegram-sync-start",
    response_model=TelegramSyncStartResponse,
    summary="Одноразовая deep link-ссылка на бота (t.me/…?start=…) для привязки Telegram",
)
async def telegram_sync_start(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> TelegramSyncStartResponse:
    return await telegram_sync_start_link(session, principal, get_redis(), settings)


@router.post(
    "/change-password",
    status_code=204,
    summary="Смена пароля: текущий и новый (JWT)",
)
async def change_password(
    body: AccountChangePasswordBody,
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> Response:
    await change_account_password(session, principal, body)
    return Response(status_code=204)


@router.delete(
    "/subscription-devices/{device_id}",
    status_code=204,
    summary="Удалить подключение",
)
async def delete_my_subscription_device(
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    device_id: int = Path(
        ...,
        ge=1,
        description="Идентификатор строки из поля id в subscription_connections (GET /api/me)",
    ),
) -> None:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    await delete_subscription_device(session, user_id=int(principal.user_id), device_id=device_id)


@router.get(
    "/support-messages",
    response_model=SupportMessagesListResponse,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="История сообщений чата поддержки",
)
async def me_support_messages(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    limit: int = Query(100, ge=1, le=200, description="Размер страницы"),
    offset: int = Query(0, ge=0, description="Смещение"),
) -> SupportMessagesListResponse:
    _require_cabinet_user(principal)
    items, total = await list_my_support_messages(
        session,
        user_id=int(principal.user_id),
        limit=limit,
        offset=offset,
    )
    return SupportMessagesListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/support-messages",
    response_model=SupportMessageRead,
    status_code=201,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="Отправить сообщение в поддержку",
)
async def me_support_message_create(
    body: SupportMessageCreate,
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> SupportMessageRead:
    _require_cabinet_user(principal)
    return await create_user_support_message(
        session,
        user_id=int(principal.user_id),
        body=body.body,
    )


@router.get(
    "/support-messages/unread-count",
    response_model=SupportUnreadCountResponse,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="Число непрочитанных ответов поддержки",
)
async def me_support_unread_count(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> SupportUnreadCountResponse:
    _require_cabinet_user(principal)
    unread = await count_unread_support_for_user(
        session,
        user_id=int(principal.user_id),
    )
    return SupportUnreadCountResponse(unread_count=unread)


@router.post(
    "/support-messages/mark-seen",
    status_code=204,
    dependencies=[Depends(require_cabinet_jwt)],
    summary="Отметить чат поддержки просмотренным",
)
async def me_support_mark_seen(
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> Response:
    _require_cabinet_user(principal)
    await mark_support_seen_for_user(session, user_id=int(principal.user_id))
    return Response(status_code=204)
