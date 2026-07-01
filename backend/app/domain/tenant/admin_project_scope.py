"""Фильтрация admin read-запросов по текущему проекту из ``X-Admin-Project``.

- Конкретный slug → ``admin_project_id()`` → один проект.
- ``__all__`` / super_admin без slug → агрегат по всем проектам.
- admin/manager без slug → только проекты из staff-JWT (не весь тенант).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.domain.tenant.project_context import get_current_project
from app.domain.tenant.staff_context import get_current_staff


def admin_project_id() -> int | None:
    """ID проекта для WHERE-фильтра или ``p_project_id`` в RPC. ``None`` = все проекты."""
    project = get_current_project()
    return int(project.id) if project is not None else None


def _resolved_project_ids(project_id: int | None = None) -> list[int] | None:
    """``None`` — без ограничения (super_admin / агрегат); ``[]`` — нет доступа."""
    pid = admin_project_id() if project_id is None else project_id
    if pid is not None:
        return [int(pid)]
    staff = get_current_staff()
    if staff is None or staff.role == "super_admin":
        return None
    return [int(p) for p in (staff.projects or [])]


def project_scope_clause(model: Any, *, project_id: int | None = None) -> ColumnElement[bool] | None:
    """Фильтр ORM по проекту; ``None`` — без ограничения (только super_admin-агрегат)."""
    ids = _resolved_project_ids(project_id)
    if ids is None:
        return None
    if not ids:
        return model.project_id < 0
    if len(ids) == 1:
        return model.project_id == ids[0]
    return model.project_id.in_(ids)


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


def user_table_project_filter_sql(
    table_alias: str = "u",
    *,
    project_id: int | None = None,
) -> str:
    """Фрагмент SQL-фильтра по project_id для raw-запросов."""
    ids = _resolved_project_ids(project_id)
    if ids is None:
        return ""
    if not ids:
        return f"AND {table_alias}.project_id < 0"
    if len(ids) == 1:
        return f"AND {table_alias}.project_id = :p_project_id"
    return f"AND {table_alias}.project_id = ANY(:p_project_ids)"


def merge_project_sql_params(
    params: dict | None = None,
    *,
    project_id: int | None = None,
) -> dict:
    """Bind-параметры для raw SQL с фильтром проекта."""
    out = dict(params or {})
    ids = _resolved_project_ids(project_id)
    if ids is None:
        return out
    if not ids:
        return out
    if len(ids) == 1:
        out["p_project_id"] = ids[0]
    else:
        out["p_project_ids"] = ids
    return out
