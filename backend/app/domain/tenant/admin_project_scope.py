"""Фильтрация admin read-запросов по текущему проекту из ``X-Admin-Project``.

``ProjectContextMiddleware`` кладёт проект в contextvars (``get_current_project``).
Админ-панель всегда шлёт заголовок ``X-Admin-Project`` (slug или ``__all__``).

- Конкретный slug → ``admin_project_id()`` возвращает ``project.id`` → фильтруем данные.
- ``__all__`` / не резолвился → ``None`` → агрегат по всем проектам (только super_admin).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.domain.tenant.project_context import get_current_project


def admin_project_id() -> int | None:
    """ID проекта для WHERE-фильтра или ``p_project_id`` в RPC. ``None`` = все проекты."""
    project = get_current_project()
    return int(project.id) if project is not None else None


def project_scope_clause(model: Any, *, project_id: int | None = None) -> ColumnElement[bool] | None:
    """``model.project_id == pid`` или ``None``, если агрегатный режим."""
    pid = admin_project_id() if project_id is None else project_id
    if pid is None:
        return None
    return model.project_id == int(pid)


def apply_project_scope(stmt: Select, model: Any, *, project_id: int | None = None) -> Select:
    clause = project_scope_clause(model, project_id=project_id)
    if clause is not None:
        stmt = stmt.where(clause)
    return stmt


def rpc_project_params(extra: dict | None = None) -> dict:
    """Параметры для SQL RPC с ``p_project_id`` (NULL = агрегат)."""
    params = dict(extra or {})
    params.setdefault("p_project_id", admin_project_id())
    return params
