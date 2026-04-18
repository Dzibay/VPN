from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import request_id_ctx

log = logging.getLogger("app.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Прокидывает X-Request-ID (или генерирует), кладёт в contextvars для логов,
    пишет access-лог: метод, путь, статус, длительность.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        header_rid = request.headers.get("X-Request-ID")
        rid = header_rid if header_rid else str(uuid.uuid4())
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except BaseException:
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "%s %s — ошибка после %.1f ms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = rid
            client = request.client.host if request.client else "-"
            log.info(
                "%s %s %d %.1fms %s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                client,
            )
            return response
        finally:
            request_id_ctx.reset(token)
