"""Единый JWT доступа (HS256): роли admin, manager и user."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

from app.config import Settings

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=14)
_DEV_FALLBACK = b"vpn-dev-access-jwt-v1"


def jwt_signing_secret(settings: Settings) -> str:
    explicit = (settings.jwt_secret or "").strip()
    if explicit:
        return explicit
    if settings.debug:
        return hashlib.sha256(_DEV_FALLBACK).hexdigest()
    raise ValueError(
        "Задайте переменную окружения JWT_SECRET "
        "(или включите DEBUG только для локальной разработки).",
    )


@dataclass(frozen=True)
class AccessClaims:
    role: Literal["admin", "user", "manager"]
    user_id: int | None


def create_access_token(
    settings: Settings,
    *,
    role: Literal["admin", "user", "manager"],
    user_id: int | None = None,
) -> str:
    secret = jwt_signing_secret(settings)
    now = datetime.now(timezone.utc)
    if user_id is None:
        raise ValueError("user_id обязателен для всех ролей JWT")
    sub = str(user_id)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def decode_access_token(token: str, settings: Settings) -> AccessClaims | None:
    try:
        secret = jwt_signing_secret(settings)
    except ValueError:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError:
        return None
    role = payload.get("role")
    sub = payload.get("sub")
    if role == "admin":
        try:
            uid = int(sub)
        except (TypeError, ValueError):
            return None
        return AccessClaims(role="admin", user_id=uid)
    if role in ("user", "manager"):
        if sub is None:
            return None
        try:
            uid = int(sub)
        except (TypeError, ValueError):
            return None
        return AccessClaims(role=role, user_id=uid)
    return None
