"""
Базовые операции над ORM-моделями (общие для таблиц в app.infrastructure.persistence.models).
Не вызывайте commit/rollback здесь — ими управляет get_db().
"""

from __future__ import annotations

from typing import Any, Mapping, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def table_select(
    session: Session,
    model: type[ModelT],
    *,
    filters: Mapping[str, Any] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[ModelT]:
    stmt = select(model)
    if filters:
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())


def table_select_one(
    session: Session,
    model: type[ModelT],
    *,
    filters: Mapping[str, Any] | None = None,
) -> ModelT | None:
    rows = table_select(session, model, filters=filters, limit=1)
    return rows[0] if rows else None


def table_insert(session: Session, instance: ModelT) -> ModelT:
    session.add(instance)
    session.flush()
    return instance


def table_update(
    session: Session,
    model: type[ModelT],
    *,
    match: Mapping[str, Any],
    values: Mapping[str, Any],
) -> int:
    stmt = update(model)
    for key, value in match.items():
        stmt = stmt.where(getattr(model, key) == value)
    stmt = stmt.values(**values)
    result = session.execute(stmt)
    return int(result.rowcount or 0)


def table_delete(
    session: Session,
    model: type[ModelT],
    *,
    match: Mapping[str, Any],
) -> int:
    stmt = delete(model)
    for key, value in match.items():
        stmt = stmt.where(getattr(model, key) == value)
    result = session.execute(stmt)
    return int(result.rowcount or 0)
