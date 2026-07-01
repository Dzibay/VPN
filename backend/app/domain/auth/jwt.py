"""Подбор API-роли по аккаунту и выдача JWT в формате, ожидаемом эндпоинтами авторизации."""

from __future__ import annotations

from typing import Literal

from app.config import Settings
from app.core.access_token import create_access_token
from app.core.exceptions import ServiceUnavailableError
from app.infrastructure.persistence.models.user import User


def jwt_role_for_user(user: User) -> Literal["user", "manager", "admin"]:
    """API-роль для JWT клиентского входа.

    Роли admin/manager живут в ``staff_users`` (отдельная админ-панель).
    Таблица ``users`` — только клиенты (``account_role='client'`` → JWT ``user``).
    """
    return "user"


def issue_access_token_or_http_error(cfg: Settings, *, role: str, user_id: int) -> str:
    """Сгенерировать JWT либо отдать HTTP 503 (когда не настроен ``JWT_SECRET``)."""
    try:
        return create_access_token(cfg, role=role, user_id=user_id)
    except ValueError as e:
        raise ServiceUnavailableError(str(e)) from e
