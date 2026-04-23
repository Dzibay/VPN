"""Единый JWT доступа (HS256): роли admin и user."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

from app.core.config import Settings

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=14)
_DERIVE_SALT = b"vpn-access-jwt-v1"
_DEV_FALLBACK = b"vpn-dev-access-jwt-v1"


def jwt_signing_secret(settings: Settings) -> str:
    explicit = (settings.jwt_secret or "").strip()
    if explicit:
        return explicit
    email = (settings.admin_email or "").strip().lower()
    pwd = (settings.admin_password or "").strip()
    if email and pwd:
        return hashlib.sha256(
            f"{email}|{pwd}".encode("utf-8") + _DERIVE_SALT,
        ).hexdigest()
    if settings.debug:
        return hashlib.sha256(_DEV_FALLBACK).hexdigest()
    raise ValueError(
        "Задайте JWT_SECRET или пару ADMIN_EMAIL + ADMIN_PASSWORD "
        "(или включите DEBUG для локальной разработки).",
    )


@dataclass(frozen=True)
class AccessClaims:
    role: Literal["admin", "user"]
    user_id: int | None


def create_access_token(
    settings: Settings,
    *,
    role: Literal["admin", "user"],
    user_id: int | None = None,
) -> str:
    secret = jwt_signing_secret(settings)
    now = datetime.now(timezone.utc)
    if role == "admin":
        sub = "admin"
    else:
        if user_id is None:
            raise ValueError("user_id обязателен для роли user")
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
        if sub != "admin":
            return None
        return AccessClaims(role="admin", user_id=None)
    if role == "user":
        if sub is None:
            return None
        try:
            uid = int(sub)
        except (TypeError, ValueError):
            return None
        return AccessClaims(role="user", user_id=uid)
    return None
