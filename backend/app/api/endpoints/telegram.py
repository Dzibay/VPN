"""Эндпоинты для бэкенда Telegram-бота (секрет X-Telegram-Bot-Secret)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select

from app.api.deps import (
    ReadonlySessionDep,
    SessionDep,
    require_telegram_bot_api_secret,
)
from app.core.config import settings
from app.domain.subscription_public_base import subscription_public_base_from_setting
from app.models.user import User
from app.schemas.account import (
    TelegramAuthBody,
    TelegramProfilePatchBody,
    TelegramSubscriptionOpenClientsResponse,
    TelegramUserPropertiesUpdateResponse,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
)
from app.schemas.users import UserRead

router = APIRouter(prefix="/telegram", tags=["public"])


@router.get(
    "/subscription-open-clients",
    response_model=TelegramSubscriptionOpenClientsResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Список VPN-клиентов для кнопок в интерфейсе бота (источник данных совпадает с GET /api/auth/me)",
)
async def subscription_open_clients() -> TelegramSubscriptionOpenClientsResponse:
    base = subscription_public_base_from_setting(settings.subscription_public_base_url)
    return TelegramSubscriptionOpenClientsResponse(
        clients=build_subscription_open_client_items(),
        public_base_url=base or None,
    )


@router.get(
    "/users/{topic_id}",
    response_model=UserRead,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Получение пользователя по значению topic_id в users.telegram_properties",
)
async def get_user_by_topic_id(
    topic_id: Annotated[
        int,
        Path(
            ge=1,
            le=9223372036854775807,
            description="Значение topic_id внутри объекта telegram_properties",
        ),
    ],
    session: ReadonlySessionDep,
) -> User:
    stmt = (
        select(User)
        .where(User.telegram_properties.contains({"topic_id": topic_id}))
        .order_by(User.id.asc())
        .limit(2)
    )
    rows = list(session.scalars(stmt).all())
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Пользователь с таким topic_id в telegram_properties не найден",
        )
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Найдено несколько пользователей с таким topic_id; уточните данные в БД",
        )
    return rows[0]


@router.patch(
    "/users/{telegram_id}",
    response_model=TelegramUserPropertiesUpdateResponse,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Частичное обновление telegram_properties (правила слияния совпадают с POST /api/auth/telegram)",
)
async def patch_user_telegram_properties(
    telegram_id: int,
    body: TelegramProfilePatchBody,
    session: SessionDep,
) -> TelegramUserPropertiesUpdateResponse:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(
            status_code=422,
            detail="Укажите хотя бы одно поле: username, first_name, last_name, topic_id",
        )
    auth_fragment = TelegramAuthBody(telegram_id=telegram_id, **patch)

    stmt = select(User).where(User.telegram_id == telegram_id).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь с таким telegram_id не найден")

    user.telegram_properties = merge_telegram_auth_profile(
        auth_fragment,
        user.telegram_properties,
    )
    session.flush()

    return TelegramUserPropertiesUpdateResponse(
        telegram_id=int(user.telegram_id or telegram_id),
        telegram_properties=user.telegram_properties,
    )
