"""Чистый ASGI-middleware для X-Request-ID и access-логов.

До рефакторинга использовался `BaseHTTPMiddleware`, у которого есть известная просадка
производительности и нюансы с обработкой исключений (Starlette 0.36+ — обсуждалось в
encode/starlette#1715, fastapi/fastapi#11203). Чистый ASGI-вариант ходит ровно на одно
``await call_next`` меньше и не оборачивает запрос в дополнительный stream.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Awaitable, Callable, MutableMapping

from app.core.logging_config import request_id_ctx

log = logging.getLogger("app.http")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def _header_get(scope: Scope, name: bytes) -> bytes | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            return v
    return None


def _header_set(message: Message, name: bytes, value: bytes) -> None:
    headers = list(message.get("headers") or [])
    headers = [(k, v) for k, v in headers if k != name]
    headers.append((name, value))
    message["headers"] = headers


def _path_with_query(scope: Scope) -> str:
    path = scope.get("path") or ""
    query = scope.get("query_string") or b""
    if query:
        try:
            return f"{path}?{query.decode('latin-1')}"
        except Exception:
            return path
    return path


def _client_host(scope: Scope) -> str:
    client = scope.get("client")
    if not client:
        return "-"
    try:
        return str(client[0])
    except (TypeError, IndexError):
        return "-"


class RequestContextMiddleware:
    """
    Прокидывает X-Request-ID (или генерирует), кладёт его в contextvars (для логов),
    пишет access-лог: метод, путь, статус, длительность.

    Чистый ASGI: ``__call__(scope, receive, send)``; не наследует ``BaseHTTPMiddleware``
    (тот переоборачивает запрос/ответ в stream, что ощутимо медленнее).
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        header_rid = _header_get(scope, b"x-request-id")
        if header_rid:
            try:
                rid = header_rid.decode("latin-1").strip() or str(uuid.uuid4())
            except Exception:
                rid = str(uuid.uuid4())
        else:
            rid = str(uuid.uuid4())

        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        rid_bytes = rid.encode("latin-1")
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                _header_set(message, b"x-request-id", rid_bytes)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "%s %s — ошибка после %.1f ms",
                scope.get("method", "?"),
                _path_with_query(scope),
                duration_ms,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            log.info(
                "%s %s %d %.1fms %s",
                scope.get("method", "?"),
                _path_with_query(scope),
                status_code,
                duration_ms,
                _client_host(scope),
            )
        finally:
            request_id_ctx.reset(token)
