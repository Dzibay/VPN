"""Проверка доступности БД для страницы статуса."""

from sqlalchemy.orm import Session

from app.infrastructure.database.operations import table_select
from app.infrastructure.persistence.models.user import User


def db_ping_ok(session: Session) -> bool:
    try:
        table_select(session, User, limit=1)
        return True
    except Exception:
        return False
