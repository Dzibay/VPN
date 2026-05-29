"""Проверка host для протоколов, требующих домен (Let's Encrypt)."""

from __future__ import annotations

import ipaddress
import re

_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def is_domain_host(host: str) -> bool:
    """True, если host похож на FQDN (не IPv4/IPv6)."""
    s = (host or "").strip().rstrip(".")
    if not s or len(s) > 253:
        return False
    try:
        ipaddress.ip_address(s)
        return False
    except ValueError:
        pass
    return bool(_DOMAIN_RE.fullmatch(s))


def normalize_grpc_service_name(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("grpc_service_name: не может быть пустым")
    if len(s) > 64:
        raise ValueError("grpc_service_name: максимум 64 символа")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", s):
        raise ValueError("grpc_service_name: только буквы, цифры, . _ -")
    return s


def normalize_ws_path(raw: str | None) -> str:
    s = (raw or "").strip() or "/vless"
    if not s.startswith("/"):
        s = "/" + s
    if len(s) > 256:
        raise ValueError("ws_path: максимум 256 символов")
    if not re.fullmatch(r"/[A-Za-z0-9._/-]*", s):
        raise ValueError("ws_path: путь должен начинаться с / (буквы, цифры, . _ - /)")
    return s
