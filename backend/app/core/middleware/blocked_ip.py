"""ASGI-middleware: отклоняет HTTP-запросы с IP из blocked_ips."""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, MutableMapping

from app.core.client_ip import header_get, resolve_client_ip
from app.domain.security.blocked_ip_cache import ensure_blocked_ips_loaded, is_ip_blocked

log = logging.getLogger("app.security.blocked_ip")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/admin/blocked-ips",
    "/api/public/ip-blocked",
    "/api/public/site-links",
)

_BLOCKED_PAGE_PATH = "/blocked"


def _is_exempt_path(path: str) -> bool:
    for prefix in _EXEMPT_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _wants_html(scope: Scope) -> bool:
    accept = (header_get(scope, b"accept") or "").lower()
    return "text/html" in accept


async def _send_redirect_blocked(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [
                [b"location", _BLOCKED_PAGE_PATH.encode("ascii")],
                [b"content-length", b"0"],
            ],
        },
    )
    await send({"type": "http.response.body", "body": b""})


async def _send_json_forbidden(scope: Scope, receive: Receive, send: Send) -> None:
    body = json.dumps(
        {"detail": "Доступ ограничен", "code": "ip_blocked"},
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                [b"content-type", b"application/json; charset=utf-8"],
                [b"content-length", str(len(body)).encode("ascii")],
                [b"x-ip-blocked", b"1"],
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
                if _wants_html(scope):
                    await _send_redirect_blocked(scope, receive, send)
                else:
                    await _send_json_forbidden(scope, receive, send)
                return

        await self.app(scope, receive, send)
