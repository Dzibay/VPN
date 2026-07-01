"""Единый JWT доступа (HS256): роли admin, manager и user."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import jwt

from app.config import Settings
from app.core.time import utc_now
from app.constants import JWT_TOKEN_TTL_DAYS

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=JWT_TOKEN_TTL_DAYS)
_DEV_FALLBACK = b"vpn-dev-access-jwt-v1"


def jwt_signing_secret(settings: Settings) -> str:
    """Подписной ключ JWT: явно заданный ``JWT_SECRET`` или dev-fallback в ``DEBUG``-режиме.

    В боевом окружении пустой секрет ловится раньше — на старте процесса
    (см. :func:`app.core.startup_checks.validate_production_secrets`); этот ``ValueError``
    остаётся как защита от ошибок последовательности импорта.
    """
    explicit = (settings.jwt_secret or "").strip()
    if explicit:
        return explicit
    if settings.debug:
        return hashlib.sha256(_DEV_FALLBACK).hexdigest()
    raise ValueError(
        "JWT_SECRET не задан и DEBUG=false: см. app.core.startup_checks.",
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
    now = utc_now()
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
    """Декодирует access-JWT. Поддерживает 2 типа токенов:

    1. Клиентский JWT (aud отсутствует): sub = users.id, role = admin|manager|user.
    2. Staff JWT (aud='staff'): sub = staff_users.id, role = super_admin|admin|manager.
       Для совместимости с legacy endpoints (require_roles('admin','manager')) staff-JWT
       мапится в AccessClaims следующим образом:
       - super_admin → role='admin' (полный доступ)
       - admin → role='admin'
       - manager → role='manager'
       ``user_id`` в этом случае = staff_users.id (не users.id!). Endpoints, которым нужен
       именно клиентский user_id (например, /api/me), не должны видеть staff-токен —
       для них используем ``require_client_access`` (см. ниже) или проверяем aud явно.
    """
    try:
        secret = jwt_signing_secret(settings)
    except ValueError:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            options={"require": ["exp", "sub", "role"], "verify_aud": False},
        )
    except jwt.PyJWTError:
        return None

    role = payload.get("role")
    sub = payload.get("sub")
    aud = payload.get("aud")

    # Staff-JWT: маппим в admin/manager для legacy require_roles.
    if aud == "staff":
        if role not in ("super_admin", "admin", "manager"):
            return None
        try:
            uid = int(sub)
        except (TypeError, ValueError):
            return None
        mapped_role: Literal["admin", "user", "manager"] = (
            "admin" if role in ("super_admin", "admin") else "manager"
        )
        return AccessClaims(role=mapped_role, user_id=uid)

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
