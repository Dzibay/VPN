"""JWT доступа к админ-API (HS256)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=7)
_DERIVE_SALT = "|vpn-admin-jwt-v1"


def admin_jwt_signing_secret(settings: Settings) -> str:
    explicit = (settings.admin_jwt_secret or "").strip()
    if explicit:
        return explicit
    pwd = (settings.admin_panel_password or "").strip()
    if not pwd:
        return ""
    return hashlib.sha256(f"{pwd}{_DERIVE_SALT}".encode()).hexdigest()


def create_admin_jwt(settings: Settings) -> str:
    secret = admin_jwt_signing_secret(settings)
    if not secret:
        raise ValueError("Нет секрета для подписи JWT")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin",
        "role": "admin",
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def verify_admin_token(token: str, settings: Settings) -> bool:
    secret = admin_jwt_signing_secret(settings)
    if not secret:
        return False
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            options={"require": ["exp", "sub", "role"]},
        )
        return payload.get("role") == "admin" and payload.get("sub") == "admin"
    except jwt.PyJWTError:
        return False
