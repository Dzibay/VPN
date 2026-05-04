"""Эндпоинты для бэкенда Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.config import settings
from app.constants import BIGINT_MAX
from app.core.dependencies import (
    ReadonlySessionDep,
    SessionDep,
    require_telegram_bot_api_secret,
)
from app.domain.models.auth import (
    TelegramProfilePatchBody,
    TelegramSubscriptionOpenClientsResponse,
    TelegramUserPropertiesUpdateResponse,
)
from app.domain.models.users import UserRead
from app.domain.services.telegram_service import (
    get_user_by_topic_id,
    patch_user_telegram_properties,
    subscription_open_clients_payload,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get(
    "/subscription-open-clients",
    response_model=TelegramSubscriptionOpenClientsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Список VPN-клиентов для кнопок в интерфейсе бота (источник данных совпадает с GET /api/auth/me)",
)
async def subscription_open_clients() -> TelegramSubscriptionOpenClientsResponse:
    return subscription_open_clients_payload(settings)


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
    return get_user_by_topic_id(session, topic_id)


@router.patch(
    "/users/{telegram_id}",
    response_model=TelegramUserPropertiesUpdateResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Частичное обновление telegram_properties (правила слияния совпадают с POST /api/auth/telegram)",
)
async def patch_user_telegram_properties_ep(
    telegram_id: int,
    body: TelegramProfilePatchBody,
    session: SessionDep,
) -> TelegramUserPropertiesUpdateResponse:
    return patch_user_telegram_properties(session, telegram_id, body)
