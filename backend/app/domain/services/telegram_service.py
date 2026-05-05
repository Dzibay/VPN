"""Бизнес-логика эндпоинтов Telegram-бота."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableEntityError
from app.core.request_subject import bind_request_subject_user
from app.domain.models.auth import (
    TelegramAuthBody,
    TelegramProfilePatchBody,
    TelegramSubscriptionOpenClientsResponse,
    TelegramUserPropertiesUpdateResponse,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
)
from app.domain.subscription.public_base import site_address_to_public_origin
from app.infrastructure.persistence.models.user import User


def subscription_open_clients_payload(settings: Settings) -> TelegramSubscriptionOpenClientsResponse:
    base = site_address_to_public_origin(settings.site_address)
    return TelegramSubscriptionOpenClientsResponse(
        clients=build_subscription_open_client_items(),
        public_base_url=base or None,
    )


async def list_telegram_user_ids(session: AsyncSession) -> list[int]:
    stmt = (
        select(User.telegram_id)
        .where(User.telegram_id.is_not(None))
        .order_by(User.telegram_id.asc())
    )
    rows = (await session.scalars(stmt)).all()
    return [int(tid) for tid in rows]


async def get_user_by_topic_id(session: AsyncSession, topic_id: int) -> User:
    stmt = (
        select(User)
        .where(User.telegram_properties.contains({"topic_id": topic_id}))
        .order_by(User.id.asc())
        .limit(2)
    )
    rows = list((await session.scalars(stmt)).all())
    if not rows:
        raise NotFoundError(
            "Пользователь с таким topic_id в telegram_properties не найден",
        )
    if len(rows) > 1:
        raise ConflictError(
            "Найдено несколько пользователей с таким topic_id; уточните данные в БД",
        )
    user = rows[0]
    bind_request_subject_user(int(user.id), source="telegram_bot_topic_lookup")
    return user


async def patch_user_telegram_properties(
    session: AsyncSession,
    telegram_id: int,
    body: TelegramProfilePatchBody,
) -> TelegramUserPropertiesUpdateResponse:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise UnprocessableEntityError(
            "Укажите хотя бы одно поле: username, first_name, last_name, topic_id",
        )
    auth_fragment = TelegramAuthBody(telegram_id=telegram_id, **patch)

    stmt = select(User).where(User.telegram_id == telegram_id).limit(1)
    user = (await session.scalars(stmt)).first()
    if user is None:
        raise NotFoundError("Пользователь с таким telegram_id не найден")

    user.telegram_properties = merge_telegram_auth_profile(
        auth_fragment,
        user.telegram_properties,
    )
    await session.flush()
    bind_request_subject_user(int(user.id), source="telegram_bot_profile_patch")

    return TelegramUserPropertiesUpdateResponse(
        telegram_id=int(user.telegram_id or telegram_id),
        telegram_properties=user.telegram_properties,
    )
