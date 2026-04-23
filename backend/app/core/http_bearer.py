"""Разбор заголовка ``Authorization: Bearer``."""

from __future__ import annotations


def bearer_token_or_none(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token or None
