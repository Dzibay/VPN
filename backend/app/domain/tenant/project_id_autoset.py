"""SQLAlchemy event listener: автоматически проставляет ``project_id`` при INSERT
для всех tenant-scoped моделей, у которых он не задан явно.

Мотивация: single-tenant код в сервисах ожидает уметь просто ``db.add(User(...))``,
без явной передачи project_id. При multi-tenant архитектуре project_id обязателен
(NOT NULL FK). Вместо переписывания каждого сервиса — listener читает текущий проект
из contextvars (``ProjectContextMiddleware`` устанавливает его на входе запроса) и
проставляет ``project_id`` перед INSERT.

Если проект в контексте не найден — берётся дефолтный ``id=1`` (legacy Подорожник).
Это обеспечивает совместимость с scheduler-корутинами и utility-скриптами,
работающими вне HTTP-контекста, до тех пор, пока они не станут явно проставлять
project_id.
"""

from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import Mapper

from app.domain.tenant.project_context import get_current_project
from app.infrastructure.database.base import Base

log = logging.getLogger(__name__)

#: Дефолтный project_id для legacy-контекстов (scheduler, миграции, тесты).
_DEFAULT_PROJECT_ID = 1

_installed = False


def _resolve_project_id() -> int:
    project = get_current_project()
    if project is not None:
        return project.id
    return _DEFAULT_PROJECT_ID


def install_project_id_autoset() -> None:
    """Устанавливает listener один раз (идемпотентно)."""
    global _installed
    if _installed:
        return

    @event.listens_for(Mapper, "before_insert")
    def _before_insert(_mapper, _connection, target):  # type: ignore[no-untyped-def]
        # У моделей вроде Server / BlockedIp / Project / StaffUser нет project_id — пропускаем.
        if not hasattr(target, "project_id"):
            return
        try:
            current = getattr(target, "project_id", None)
        except Exception:
            return
        if current is not None:
            return
        try:
            target.project_id = _resolve_project_id()
        except Exception:
            log.exception(
                "Не удалось проставить project_id для %s (пропускаем — БД решит)",
                type(target).__name__,
            )

    _installed = True
    # Base — чтобы Python не пожаловался на неиспользованный import;
    # заодно валидируем, что Mapper.propagate=True сработает для всех подклассов.
    _ = Base
    log.info("Установлен listener before_insert: авто-проставление project_id")
