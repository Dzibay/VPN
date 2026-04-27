import secrets
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.security_bearer import bearer_jwt
from app.core.access_token import AccessClaims, decode_access_token
from app.core.config import get_settings
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


def _token_strict(creds: HTTPAuthorizationCredentials | None) -> str | None:
    if creds is None or not creds.credentials:
        return None
    s = str(creds.credentials).strip()
    return s or None


def require_admin(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
) -> None:
    settings = get_settings()
    if not _admin_protection_enabled(settings):
        return
    token = _token_strict(creds)
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
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
) -> BearerPrincipal:
    settings = get_settings()
    token = _token_strict(creds)
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


def require_telegram_bot_api_secret(
    x_telegram_bot_secret: Annotated[str | None, Header()] = None,
) -> None:
    """
    Тот же секрет, что и для POST /api/auth/telegram и GET /api/telegram/subscription-open-clients
    (заголовок X-Telegram-Bot-Secret). TELEGRAM_BOT_API_SECRET в env; пусто — 503.
    """
    settings = get_settings()
    expected = (settings.telegram_bot_api_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="TELEGRAM_BOT_API_SECRET не задан: эндпоинт отключён",
        )
    got = (x_telegram_bot_secret or "").strip()
    if not got or not secrets.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="Недействительный секрет бота")
