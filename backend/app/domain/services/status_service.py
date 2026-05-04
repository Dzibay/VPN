"""Проверка доступности БД для страницы статуса."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("app.status_service")


async def db_ping_ok(session: AsyncSession) -> bool:
    """Лёгкий ping БД через ``SELECT 1`` (без обращения к таблицам)."""
    try:
        await session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        log.warning("db_ping_ok: соединение с БД недоступно", exc_info=True)
        return False
