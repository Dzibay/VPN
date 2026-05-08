"""Эндпоинты для бэкенда Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query

from app.config import settings
from app.constants import BIGINT_MAX
from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    require_telegram_bot_api_secret,
)
from app.domain.auth.jwt import jwt_role_for_user
from app.domain.models.auth import (
    TelegramKnownUserIdsResponse,
    TelegramSiteLinkStartBody,
    TelegramSiteLinkStartResponse,
    TelegramSubscriptionOpenClientsResponse,
    TelegramWebLinkBody,
    TelegramWebLinkResponse,
)
from app.domain.models.payments import (
    TributeSubscriptionResponse,
    TributeWebhookAck,
    TributeWebhookTestBody,
)
from app.domain.models.telegram_notification_tasks import (
    TelegramNotificationTasksListResponse,
    TelegramTasksAckBody,
    TelegramTasksAckResponse,
)
from app.domain.models.referral_links import ReferralMeResponse
from app.domain.models.users import UserRead
from app.domain.services.telegram_auth_service import (
    telegram_link_web_account,
    telegram_site_link_start,
)
from app.domain.services.me_service import delete_subscription_device
from app.domain.services.referral_links_service import (
    referral_me_for_user,
    referral_me_user_id_from_bearer,
)
from app.domain.services.telegram_notification_tasks_service import (
    acknowledge_notification_tasks_with_statuses,
    list_pending_notification_tasks,
)
from app.domain.services.tribute_service import (
    process_tribute_webhook_event,
    tribute_subscription_public_response,
)
from app.domain.services.telegram_service import (
    get_user_by_topic_id,
    list_telegram_user_ids,
    require_user_by_telegram_id,
    subscription_open_clients_payload,
)
from app.domain.users.xray_sync_queue import enqueue_sync_xray_clients_all_servers
from app.infrastructure.cache import get_redis

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post(
    "/link",
    response_model=TelegramWebLinkResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Привязка Telegram к учётной записи по одноразовому токену из личного кабинета",
)
async def telegram_link_web_account_ep(
    body: TelegramWebLinkBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramWebLinkResponse:
    resp = await telegram_link_web_account(session, body, get_redis(), settings)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return resp


@router.post(
    "/site-link/start",
    response_model=TelegramSiteLinkStartResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Ссылка на сайт: форма привязки email/пароля или вход в кабинет по JWT (поля site_url и has_account)",
)
async def telegram_site_link_start_ep(
    body: TelegramSiteLinkStartBody,
    session: ReadonlySessionDep,
) -> TelegramSiteLinkStartResponse:
    return await telegram_site_link_start(session, body, get_redis(), settings)


@router.get(
    "/referral/me",
    response_model=ReferralMeResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Персональная реферальная ссылка (как GET /api/referral/me), по telegram_id и секрету бота",
    description="Та же логика, что GET /api/referral/me: персональная ссылка для учётной записи по роли в БД.",
)
async def telegram_referral_me(
    session: SessionDep,
    telegram_id: Annotated[
        int,
        Query(
            ge=1,
            le=BIGINT_MAX,
            description="Telegram user id (Bot API)",
        ),
    ],
) -> ReferralMeResponse:
    user = await require_user_by_telegram_id(session, telegram_id)
    principal = BearerPrincipal(role=jwt_role_for_user(user), user_id=user.id)
    uid = referral_me_user_id_from_bearer(principal)
    return await referral_me_for_user(session, uid, settings)


@router.delete(
    "/subscription-devices/{device_id}",
    status_code=204,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Удалить подключение (как DELETE /api/me/subscription-devices/{device_id}), по telegram_id и секрету бота",
)
async def telegram_delete_subscription_device_ep(
    session: SessionDep,
    device_id: Annotated[int, Path(ge=1, description="Идентификатор строки subscription_devices")],
    telegram_id: Annotated[
        int,
        Query(
            ge=1,
            le=BIGINT_MAX,
            description="Telegram user id (Bot API)",
        ),
    ],
) -> None:
    user = await require_user_by_telegram_id(session, telegram_id)
    await delete_subscription_device(session, user_id=int(user.id), device_id=device_id)


@router.get(
    "/subscription-open-clients",
    response_model=TelegramSubscriptionOpenClientsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Список VPN-клиентов для кнопок в интерфейсе бота (источник данных совпадает с GET /api/me)",
)
async def subscription_open_clients() -> TelegramSubscriptionOpenClientsResponse:
    return subscription_open_clients_payload(settings)


@router.get(
    "/users",
    response_model=TelegramKnownUserIdsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Все известные telegram_id пользователей (users.telegram_id IS NOT NULL)",
)
async def list_telegram_users_ep(session: ReadonlySessionDep) -> TelegramKnownUserIdsResponse:
    ids = await list_telegram_user_ids(session)
    return TelegramKnownUserIdsResponse(telegram_ids=ids)


@router.get(
    "/users/{topic_id}",
    response_model=UserRead,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Получение пользователя по значению topic_id в users.telegram_properties",
)
async def get_user_by_topic_id_ep(
    topic_id: Annotated[
        int,
        Path(
            ge=1,
            le=BIGINT_MAX,
            description="Значение topic_id внутри объекта telegram_properties",
        ),
    ],
    session: ReadonlySessionDep,
) -> UserRead:
    return await get_user_by_topic_id(session, topic_id)


@router.get(
    "/payments/tribute-subscription",
    response_model=TributeSubscriptionResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Подписка Tribute (рекуррентная): ссылка для кнопки оплаты в боте",
)
async def telegram_tribute_subscription_ep() -> TributeSubscriptionResponse:
    return tribute_subscription_public_response(settings)


@router.post(
    "/payments/tribute-webhook-test",
    response_model=TributeWebhookAck,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Тестовый прогон Tribute-webhook без HMAC (X-Telegram-Bot-Secret вместо trbt-signature)",
    description=(
        "Только для ручной отладки в Swagger / Postman: вызывает ту же бизнес-логику, что и "
        "POST /api/payments/tribute/webhook (запись в payments, продление подписки, реф-бонус, "
        "идемпотентность по subscription_id+expires_at), но **без проверки HMAC** — защищён "
        "только заголовком X-Telegram-Bot-Secret. В Tribute этот URL указывать НЕ нужно."
    ),
)
async def telegram_tribute_webhook_test_ep(
    session: SessionDep,
    body: TributeWebhookTestBody,
) -> TributeWebhookAck:
    return await process_tribute_webhook_event(
        session,
        settings=settings,
        name=body.name,
        payload=body.payload.model_dump(mode="json"),
    )


@router.get(
    "/notification-tasks",
    response_model=TelegramNotificationTasksListResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Невыполненные задачи оповещения (notify_ref_*, notify_payment, notify_sub_expire_*)",
    description="С joined telegram_id получателя и реферала (если есть в users).",
)
async def telegram_list_notification_tasks_ep(
    session: ReadonlySessionDep,
) -> TelegramNotificationTasksListResponse:
    return await list_pending_notification_tasks(session)


@router.post(
    "/notification-tasks/completed",
    response_model=TelegramTasksAckResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Отметить задачи оповещения как completed/failed",
    description="По переданным id для pending-задач ставится статус completed или failed (только типы задач оповещения).",
)
async def telegram_complete_notification_tasks_ep(
    session: SessionDep,
    body: TelegramTasksAckBody,
) -> TelegramTasksAckResponse:
    completed_ids, failed_ids = await acknowledge_notification_tasks_with_statuses(
        session,
        completed_task_ids=body.completed_task_ids,
        failed_task_ids=body.failed_task_ids,
    )
    return TelegramTasksAckResponse(completed_task_ids=completed_ids, failed_task_ids=failed_ids)
