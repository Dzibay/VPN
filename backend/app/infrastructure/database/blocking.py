"""Запуск блокирующей sync-работы с БД из async-кода.

Многие доменные сервисы выполняли один и тот же шаблон: открыть ``SessionLocal()``,
поработать sync-SQLAlchemy / httpx (Prometheus) / Redis вне event loop и закрыть сессию,
обернув всё в ``run_in_threadpool``. Этот хелпер убирает повторяющийся
``db = SessionLocal(); try/finally: db.close()`` из каждой такой функции.

Использование::

    def _summary_blocking(db: Session, server_id: int) -> Summary:
        ...  # обычный sync-код с db

    async def server_summary(server_id: int) -> Summary:
        return await run_blocking_with_session(_summary_blocking, server_id)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.infrastructure.database.session import SessionLocal

T = TypeVar("T")


def _call_with_session(fn: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    db: Session = SessionLocal()
    try:
        return fn(db, *args, **kwargs)
    finally:
        db.close()


async def run_blocking_with_session(fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Выполнить ``fn(db, *args, **kwargs)`` в threadpool со свежей sync-сессией.

    Сессия создаётся и закрывается вокруг вызова; коммит — на усмотрение ``fn``
    (большинство таких функций только читают). ``fn`` не должна содержать ``await``.
    """
    return await run_in_threadpool(_call_with_session, fn, *args, **kwargs)
