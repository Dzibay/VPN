"""ASGI-middleware: отклоняет HTTP-запросы с IP из blocked_ips."""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, MutableMapping

from app.core.client_ip import resolve_client_ip
from app.domain.security.blocked_ip_cache import ensure_blocked_ips_loaded, is_ip_blocked

log = logging.getLogger("app.security.blocked_ip")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/staff/blocked-ips",
)


def _is_exempt_path(path: str) -> bool:
    for prefix in _EXEMPT_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


async def _send_json_forbidden(scope: Scope, receive: Receive, send: Send) -> None:
    body = json.dumps({"detail": "Доступ с этого IP заблокирован"}, ensure_ascii=False).encode(
        "utf-8",
    )
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                [b"content-type", b"application/json; charset=utf-8"],
                [b"content-length", str(len(body)).encode("ascii")],
            ],
        },
    )
    await send({"type": "http.response.body", "body": body})


class BlockedIpMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if not _is_exempt_path(path):
            client_ip = resolve_client_ip(scope)
            blocked = await ensure_blocked_ips_loaded()
            if is_ip_blocked(client_ip, blocked):
                log.warning("Заблокированный IP %s — %s %s", client_ip, scope.get("method"), path)
                await _send_json_forbidden(scope, receive, send)
                return

        await self.app(scope, receive, send)
