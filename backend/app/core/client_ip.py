"""Определение IP клиента из ASGI scope (прокси-заголовки и TCP peer)."""

from __future__ import annotations

import ipaddress
from typing import Any, MutableMapping

Scope = MutableMapping[str, Any]


def _header_get(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            try:
                return v.decode("latin-1").strip()
            except Exception:
                return None
    return None


def _parse_ip(value: str) -> str | None:
    s = value.strip()
    if not s:
        return None
    if s.startswith("[") and "]" in s:
        s = s[1 : s.index("]")]
    elif s.count(":") == 1 and "." in s:
        s = s.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(s))
    except ValueError:
        return None


def resolve_client_ip(scope: Scope) -> str | None:
    """
    IP клиента: первый валидный адрес из X-Forwarded-For, иначе X-Real-IP, иначе TCP peer.
    """
    xff = _header_get(scope, b"x-forwarded-for")
    if xff:
        for part in xff.split(","):
            ip = _parse_ip(part)
            if ip:
                return ip

    xri = _header_get(scope, b"x-real-ip")
    if xri:
        ip = _parse_ip(xri)
        if ip:
            return ip

    client = scope.get("client")
    if client:
        try:
            return str(client[0])
        except (TypeError, IndexError):
            pass
    return None
