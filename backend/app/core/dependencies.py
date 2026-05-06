import secrets
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security_bearer import bearer_jwt
from app.config import get_settings
from app.core.access_token import AccessClaims, decode_access_token, jwt_signing_secret
from app.core.request_subject import bind_request_subject_user
from app.core.exceptions import ForbiddenError, ServiceUnavailableError, UnauthorizedError
from app.infrastructure.database.session import get_db, get_db_readonly

SessionDep = Annotated[AsyncSession, Depends(get_db)]
ReadonlySessionDep = Annotated[AsyncSession, Depends(get_db_readonly)]


def jwt_gate_active(settings=None) -> bool:
    """
    Защита Bearer включена, если можно вычислить секрет подписи JWT
    (JWT_SECRET задан, либо DEBUG с локальным ключом).
    Пока секрет недоступен — зависимости «require_*» не требуют токена (режим как раньше).
    """
    if settings is None:
        settings = get_settings()
    try:
        jwt_signing_secret(settings)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class BearerPrincipal:
    role: Literal["admin", "user", "manager"]
    user_id: int | None


def _claims_to_principal(claims: AccessClaims) -> BearerPrincipal:
    return BearerPrincipal(role=claims.role, user_id=claims.user_id)


async def apply_request_subject_from_bearer_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
) -> None:
    """Без ошибок: если в запросе валидный Bearer JWT — сохраняем user_id и роль в контексте запроса."""
    settings = get_settings()
    if not jwt_gate_active(settings):
        return
    token = _token_strict(creds)
    if not token:
        return
    claims = decode_access_token(token, settings)
    if claims is None or claims.user_id is None:
        return
    bind_request_subject_user(claims.user_id, source=f"jwt_{claims.role}")


def _token_strict(creds: HTTPAuthorizationCredentials | None) -> str | None:
    if creds is None or not creds.credentials:
        return None
    s = str(creds.credentials).strip()
    return s or None


def require_roles(
    *allowed_roles: Literal["admin", "manager", "user"],
):
    """
    Фабрика зависимостей FastAPI: JWT обязателен (если включён jwt_gate_active),
    роль из токена должна входить в allowed_roles.
    - admin — полный доступ к админ-API и страницам /admin (кроме только рефералов).
    - manager — API реферальных ссылок и журнала HTTP-запросов, GET /users (сводка без токенов),
      UI /admin/referrals, /admin/logs, /admin/users/analytics, /admin/users/registrations-by-date,
      /admin/users/subscription-user-agent-stats
      (GET /api/users/daily-stats, stats_by_date), /admin/funnel,
      CRUD /api/staff/chart-events.
    - user — клиентский JWT (для эндпоинтов, где явно разрешён просмотр своих данных).
    """
    allowed = frozenset(allowed_roles)

    async def _dependency(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
    ) -> None:
        settings = get_settings()
        if not jwt_gate_active(settings):
            return
        token = _token_strict(creds)
        if not token:
            raise UnauthorizedError(
                detail="Требуется вход",
                headers={"WWW-Authenticate": "Bearer"},
            )
        claims = decode_access_token(token, settings)
        if claims is None:
            raise UnauthorizedError(
                detail="Недействительный или просроченный токен",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if claims.role not in allowed:
            raise ForbiddenError(detail="Недостаточно прав")

    return _dependency


# Частые комбинации (удобный импорт Depends(require_admin) и т.д.)
require_admin = require_roles("admin")
require_referrals_staff = require_roles("admin", "manager")

StaffUserListMode = Literal["open", "admin", "manager"]


def require_staff_user_list_access(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
) -> StaffUserListMode:
    """
    GET /api/users: при выключенном JWT-гейте — полные поля как у админа;
    при включённом — только admin или manager (у manager в ответе обнуляются token и vless_uuid).
    """
    settings = get_settings()
    if not jwt_gate_active(settings):
        return "open"
    token = _token_strict(creds)
    if not token:
        raise UnauthorizedError(
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(token, settings)
    if claims is None:
        raise UnauthorizedError(
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if claims.role == "admin":
        return "admin"
    if claims.role == "manager":
        return "manager"
    raise ForbiddenError(detail="Недостаточно прав")


def get_bearer_principal_dep(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
) -> BearerPrincipal:
    settings = get_settings()
    token = _token_strict(creds)
    if not token:
        raise UnauthorizedError(
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(token, settings)
    if claims is None:
        raise UnauthorizedError(
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _claims_to_principal(claims)


def require_telegram_bot_api_secret(
    x_telegram_bot_secret: Annotated[str | None, Header()] = None,
) -> None:
    """
    Тот же секрет, что и для POST /api/auth/telegram, POST /api/telegram/link, POST /api/telegram/site-link/start,
    GET /api/telegram/referral/me, DELETE /api/telegram/subscription-devices/{device_id},
    POST /api/telegram/payments, PATCH /api/telegram/payments/{payment_id},
    GET /api/telegram/notification-tasks, POST /api/telegram/notification-tasks/completed,
    GET /api/telegram/users, GET /api/telegram/users/{topic_id} и
    GET /api/telegram/subscription-open-clients (заголовок X-Telegram-Bot-Secret).
    TELEGRAM_BOT_API_SECRET в env; пусто — 503.
    """
    settings = get_settings()
    expected = (settings.telegram_bot_api_secret or "").strip()
    if not expected:
        raise ServiceUnavailableError(detail="TELEGRAM_BOT_API_SECRET не задан: эндпоинт отключён")
    got = (x_telegram_bot_secret or "").strip()
    if not got or not secrets.compare_digest(got, expected):
        raise UnauthorizedError(detail="Недействительный секрет бота")
