"""JWT доступа пользовательского портала (HS256), отдельно от админского JWT."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from app.core.admin_token import admin_jwt_signing_secret
from app.core.config import Settings

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=14)
_DEV_FALLBACK = b"vpn-dev-portal-user-jwt-v1"


def user_jwt_signing_secret(settings: Settings) -> str:
    explicit = (settings.user_jwt_secret or "").strip()
    if explicit:
        return explicit
    base = admin_jwt_signing_secret(settings)
    if base:
        return hashlib.sha256(f"{base}|vpn-portal-user-v1".encode()).hexdigest()
    if settings.debug:
        return hashlib.sha256(_DEV_FALLBACK).hexdigest()
    raise ValueError(
        "Задайте USER_JWT_SECRET или ADMIN_JWT_SECRET / ADMIN_PANEL_PASSWORD "
        "для подписи JWT портала (или включите DEBUG для локальной разработки).",
    )


def create_user_jwt(settings: Settings, *, user_id: int) -> str:
    secret = user_jwt_signing_secret(settings)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "user",
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def verify_user_token_user_id(token: str, settings: Settings) -> int | None:
    try:
        secret = user_jwt_signing_secret(settings)
    except ValueError:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            options={"require": ["exp", "sub", "role"]},
        )
        if payload.get("role") != "user":
            return None
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
