"""Резолвинг бренд-имени и других brand-полей текущего проекта.

Используется вместо константы ``app.constants.BRAND_NAME``: если в contextvars есть
активный проект (см. ``ProjectContextMiddleware``) — берём ``project.brand['brand_name']``,
иначе fallback на legacy-константу (обратная совместимость для случаев вне HTTP-контекста —
scheduler, миграции, тесты).
"""

from __future__ import annotations

from app.constants import BRAND_NAME as _LEGACY_BRAND_NAME
from app.domain.tenant.project_context import get_current_project


def resolve_brand_name() -> str:
    project = get_current_project()
    if project is not None:
        name = project.brand_name
        if name:
            return name
    return _LEGACY_BRAND_NAME


def resolve_brand_field(key: str, default: str | None = None) -> str | None:
    project = get_current_project()
    if project is not None and project.brand:
        v = project.brand.get(key)
        if v:
            return str(v)
    return default
