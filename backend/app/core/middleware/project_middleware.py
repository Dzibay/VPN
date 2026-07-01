"""ASGI middleware: резолвит текущий проект по Host / URL / bot-secret и
кладёт его в ``request.state.project`` + contextvars.

Не бросает 4xx: если проект не найден — endpoint сам решает, что делать
(dependency ``require_project`` вернёт 404).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, MutableMapping

from app.config import get_settings
from app.core.staff_token import decode_staff_token
from app.domain.tenant.project_context import (
    ProjectContext,
    reset_current_project,
    set_current_project,
)
from app.domain.tenant.project_resolver import resolve_project
from app.domain.tenant.staff_context import reset_current_staff, set_current_staff

log = logging.getLogger("app.tenant")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def _extract_bearer_token(scope: Scope) -> str | None:
    for key, value in scope.get("headers") or ():
        if key != b"authorization":
            continue
        try:
            raw = value.decode("latin-1").strip()
        except Exception:
            return None
        if raw.lower().startswith("bearer "):
            token = raw[7:].strip()
            return token or None
    return None


class ProjectContextMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        project: ProjectContext | None = None
        try:
            project = await resolve_project(scope)
        except Exception:
            # Резолвинг — best-effort. Ошибки в БД не должны валить весь запрос.
            log.exception("Ошибка резолвинга проекта")

        # request.state — стандартный способ прокинуть в endpoint.
        # ASGI scope.state станет доступен через ``request.state`` в FastAPI Request.
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["project"] = project
        else:
            try:
                setattr(state, "project", project)
            except Exception:
                pass

        token = set_current_project(project)
        staff_token = set_current_staff(None)
        bearer = _extract_bearer_token(scope)
        if bearer:
            try:
                staff_claims = decode_staff_token(bearer, get_settings())
                if staff_claims is not None:
                    staff_token = set_current_staff(staff_claims)
            except Exception:
                log.exception("Ошибка декодирования staff-JWT")
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_staff(staff_token)
            reset_current_project(token)
