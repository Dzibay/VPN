from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.access_token import AccessClaims, decode_access_token
from app.core.config import get_settings
from app.core.http_bearer import bearer_token_or_none
from app.database.session import get_db, get_db_readonly
SessionDep = Annotated[Session, Depends(get_db)]
ReadonlySessionDep = Annotated[Session, Depends(get_db_readonly)]


def _admin_protection_enabled(settings) -> bool:
    email = (settings.admin_email or "").strip()
    pwd = (settings.admin_password or "").strip()
    return bool(email and pwd)


@dataclass(frozen=True)
class BearerPrincipal:
    role: Literal["admin", "user"]
    user_id: int | None


def _claims_to_principal(claims: AccessClaims) -> BearerPrincipal:
    return BearerPrincipal(role=claims.role, user_id=claims.user_id)


def require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if not _admin_protection_enabled(settings):
        return
    token = bearer_token_or_none(authorization)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(token, settings)
    if claims is None or claims.role != "admin":
        raise HTTPException(
            status_code=401,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_bearer_principal_dep(
    authorization: Annotated[str | None, Header()] = None,
) -> BearerPrincipal:
    settings = get_settings()
    token = bearer_token_or_none(authorization)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(token, settings)
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _claims_to_principal(claims)

