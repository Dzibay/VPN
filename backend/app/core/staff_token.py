"""JWT для персонала (staff_users). Отдельный ``aud`` от access-token обычных клиентов.

Payload: ``{sub, role, projects, aud='staff', iat, exp}``, где:
- ``sub`` — ``staff_users.id``.
- ``role`` — ``super_admin`` | ``admin`` | ``manager`` (глобальная роль).
- ``projects`` — список ``project_id`` из ``staff_user_project_access``; либо ``"all"`` для super_admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

import jwt

from app.config import Settings
from app.core.access_token import jwt_signing_secret
from app.core.time import utc_now
from app.constants import JWT_TOKEN_TTL_DAYS

_JWT_ALG = "HS256"
_TOKEN_TTL = timedelta(days=JWT_TOKEN_TTL_DAYS)
_STAFF_AUDIENCE = "staff"

StaffRole = Literal["super_admin", "admin", "manager"]


@dataclass(frozen=True)
class StaffClaims:
    staff_user_id: int
    role: StaffRole
    #: Список project_id, к которым есть доступ. ``None`` для super_admin (доступ ко всем).
    projects: list[int] | None


def create_staff_token(
    settings: Settings,
    *,
    staff_user_id: int,
    role: StaffRole,
    projects: list[int] | None,
) -> str:
    secret = jwt_signing_secret(settings)
    now = utc_now()
    payload: dict[str, object] = {
        "sub": str(staff_user_id),
        "role": role,
        "aud": _STAFF_AUDIENCE,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    if role == "super_admin":
        payload["projects"] = "all"
    else:
        payload["projects"] = projects or []
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def decode_staff_token(token: str, settings: Settings) -> StaffClaims | None:
    try:
        secret = jwt_signing_secret(settings)
    except ValueError:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            audience=_STAFF_AUDIENCE,
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError:
        return None

    role = payload.get("role")
    sub = payload.get("sub")
    if role not in ("super_admin", "admin", "manager"):
        return None
    try:
        uid = int(sub)
    except (TypeError, ValueError):
        return None

    projects_claim = payload.get("projects")
    projects: list[int] | None
    if role == "super_admin" or projects_claim == "all":
        projects = None
    elif isinstance(projects_claim, list):
        try:
            projects = [int(p) for p in projects_claim]
        except (TypeError, ValueError):
            return None
    else:
        projects = []

    return StaffClaims(staff_user_id=uid, role=role, projects=projects)  # type: ignore[arg-type]
