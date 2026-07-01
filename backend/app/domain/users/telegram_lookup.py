"""Поиск пользователей Telegram в рамках одного проекта (multi-tenant)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.request_subject import bind_request_subject_user
from app.domain.tenant.project_context import ProjectContext, get_current_project
from app.infrastructure.persistence.models.user import User


async def user_by_telegram_id_in_project(
    session: AsyncSession,
    telegram_id: int,
    project_id: int,
) -> User | None:
    stmt = (
        select(User)
        .where(
            User.telegram_id == int(telegram_id),
            User.project_id == int(project_id),
        )
        .limit(1)
    )
    return (await session.scalars(stmt)).first()


def require_project_context(project: ProjectContext | None = None) -> ProjectContext:
    ctx = project or get_current_project()
    if ctx is None:
        raise NotFoundError("Проект не найден для запроса бота")
    return ctx


async def require_user_by_telegram_id_in_project(
    session: AsyncSession,
    telegram_id: int,
    *,
    project: ProjectContext | None = None,
    bind_source: str = "telegram_bot_id_lookup",
) -> User:
    ctx = require_project_context(project)
    user = await user_by_telegram_id_in_project(session, telegram_id, ctx.id)
    if user is None:
        raise NotFoundError("Пользователь с таким telegram_id не найден")
    bind_request_subject_user(int(user.id), source=bind_source)
    return user
