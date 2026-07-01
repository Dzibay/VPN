"""Бизнес-логика эндпоинтов Telegram-бота."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.request_subject import bind_request_subject_user
from app.domain.models.auth import (
    TelegramSubscriptionOpenClientsResponse,
    build_subscription_open_client_items,
)
from app.domain.subscription.public_base import site_address_to_public_origin
from app.domain.tenant.project_context import ProjectContext, get_current_project
from app.domain.users.telegram_lookup import (
    require_project_context,
    require_user_by_telegram_id_in_project,
    user_by_telegram_id_in_project,
)
from app.infrastructure.persistence.models.user import User


def subscription_open_clients_payload(
    settings: Settings,
    project: ProjectContext | None = None,
) -> TelegramSubscriptionOpenClientsResponse:
    ctx = project or get_current_project()
    base = site_address_to_public_origin(
        ctx.primary_domain if ctx is not None else settings.site_address
    )
    return TelegramSubscriptionOpenClientsResponse(
        clients=build_subscription_open_client_items(),
        public_base_url=base or None,
    )


async def require_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
    *,
    project: ProjectContext | None = None,
) -> User:
    return await require_user_by_telegram_id_in_project(
        session, telegram_id, project=project
    )


async def get_user_by_topic_id(
    session: AsyncSession,
    topic_id: int,
    *,
    project: ProjectContext | None = None,
) -> User:
    ctx = require_project_context(project)
    stmt = (
        select(User)
        .where(
            User.project_id == int(ctx.id),
            User.telegram_properties.contains({"topic_id": topic_id}),
        )
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


async def find_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
    *,
    project: ProjectContext | None = None,
) -> User | None:
    ctx = require_project_context(project)
    return await user_by_telegram_id_in_project(session, telegram_id, ctx.id)
