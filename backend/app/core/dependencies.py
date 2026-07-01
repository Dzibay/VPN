import secrets
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import unquote_plus

from fastapi import Cookie, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security_bearer import bearer_jwt
from app.config import get_settings
from app.core.access_token import AccessClaims, decode_access_token, jwt_signing_secret
from app.core.request_subject import bind_request_subject_user
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.domain.tenant.project_cache import get_project_by_bot_secret, get_project_by_id
from app.domain.tenant.project_context import ProjectContext, set_current_project
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
      /api/admin/blocked-ips — только admin;
      PATCH /users/{id} только traffic_limit_bytes,
      UI /admin/referrals, /admin/logs, /admin/payments, /admin/tasks, /admin/users/analytics,
      /admin/users/{id}/analytics,
      /admin/users/registrations-by-date, /admin/users/subscription-user-agent-stats
      (GET /api/users/daily-stats, stats_by_date), GET /api/users/daily-payments-expiry-bars (?month=YYYY-MM UTC), /admin/funnel,
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

# GET /swagger: только cookie (кнопка в админке выставляет Path=/swagger, без Bearer в браузере).
SWAGGER_STAFF_JWT_COOKIE = "SwaggerStaffJwt"


async def require_swagger_staff_cookie(
    swagger_staff_jwt: Annotated[str | None, Cookie(alias=SWAGGER_STAFF_JWT_COOKIE)] = None,
) -> None:
    settings = get_settings()
    if not jwt_gate_active(settings):
        return
    if not swagger_staff_jwt:
        raise UnauthorizedError(detail="Доступ запрещен")
    token = unquote_plus(swagger_staff_jwt.strip()) or None
    if not token:
        raise UnauthorizedError(detail="Доступ запрещен")
    claims = decode_access_token(token, settings)
    if claims is None:
        raise UnauthorizedError(detail="Недействительный или просроченный токен")
    if claims.role not in frozenset(("admin", "manager")):
        raise ForbiddenError(detail="Недостаточно прав")


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


def require_referral_links_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """
    POST /api/referral/external/links (заголовок X-API-Key).
    REFERRAL_LINKS_API_KEY в env; пусто — 503.
    """
    settings = get_settings()
    expected = (settings.referral_links_api_key or "").strip()
    if not expected:
        raise ServiceUnavailableError(
            detail="REFERRAL_LINKS_API_KEY не задан: эндпоинт отключён",
        )
    got = (x_api_key or "").strip()
    if not got or not secrets.compare_digest(got, expected):
        raise UnauthorizedError(detail="Недействительный API-ключ")


async def require_telegram_bot_api_secret(
    request: Request,
    x_telegram_bot_secret: Annotated[str | None, Header()] = None,
) -> ProjectContext:
    """
    Multi-tenant: секрет ищется в ``projects.telegram_bot_api_secret`` (per-project).
    Возвращает найденный проект — endpoint может использовать его напрямую.

    Fallback: если проект по секрету не найден, но глобальный ``settings.telegram_bot_api_secret``
    задан и совпадает — принимаем секрет и берём дефолтный проект id=1 (обратная совместимость
  для бота Подорожника). Секрет другого проекта без записи в БД → 401, не подмена на id=1.
    """
    got = (x_telegram_bot_secret or "").strip()
    if not got:
        raise UnauthorizedError(detail="Недействительный секрет бота")

    project = await get_project_by_bot_secret(got)
    if project is None:
        settings = get_settings()
        expected = (settings.telegram_bot_api_secret or "").strip()
        if expected and secrets.compare_digest(got, expected):
            project = await get_project_by_id(1)
            if project is None:
                raise ServiceUnavailableError(
                    detail="Дефолтный проект (id=1) отсутствует — миграция не выполнена",
                )
        else:
            if not expected:
                raise ServiceUnavailableError(
                    detail="TELEGRAM_BOT_API_SECRET не задан: эндпоинт отключён",
                )
            raise UnauthorizedError(detail="Недействительный секрет бота")

    request.state.project = project
    set_current_project(project)
    return project


# =====================================================================
# Multi-tenant dependencies: резолвинг проекта по Host / bot-secret / URL-slug.
# ProjectContextMiddleware кладёт проект в request.state.project (может быть None).
# =====================================================================


def get_project_optional(request: Request) -> ProjectContext | None:
    """Возвращает текущий проект или None (для health/prometheus SD и admin endpoints)."""
    return getattr(request.state, "project", None)


def require_project(request: Request) -> ProjectContext:
    """404, если проект не резолвится (для tenant-scoped публичных endpoints).

    Используется в endpoints, где хост запроса обязан принадлежать известному проекту
    (страницы SPA, публичные API кабинета, payment webhooks, bot API).
    """
    project = getattr(request.state, "project", None)
    if project is None:
        raise NotFoundError(detail="Проект не найден для этого домена")
    return project


# =====================================================================
# Staff auth / admin dependencies.
# =====================================================================


def _extract_staff_token(creds: HTTPAuthorizationCredentials | None) -> str | None:
    return _token_strict(creds)


async def get_staff_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)] = None,
):
    """Возвращает ``StaffClaims`` или падает 401/403."""
    from app.core.staff_token import decode_staff_token

    settings = get_settings()
    token = _extract_staff_token(creds)
    if not token:
        raise UnauthorizedError(
            detail="Требуется вход персонала",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_staff_token(token, settings)
    if claims is None:
        raise UnauthorizedError(detail="Недействительный staff-токен")
    return claims


def require_staff_role(*allowed_roles: str):
    """Depends-фабрика: требует staff-JWT + одна из перечисленных ролей."""
    allowed = frozenset(allowed_roles) if allowed_roles else None

    async def _dep(claims=Depends(get_staff_principal)):
        if allowed is not None and claims.role not in allowed:
            raise ForbiddenError(detail="Недостаточно прав персонала")
        return claims

    return _dep


require_staff_any = require_staff_role()
require_super_admin = require_staff_role("super_admin")


async def require_admin_project(
    request: Request,
    claims=Depends(get_staff_principal),
) -> ProjectContext | None:
    """Резолвит проект админ-запроса из заголовка ``X-Admin-Project`` (slug) или query ``?project=slug``.

    Возвращает:
    - ``ProjectContext`` — конкретный проект (staff должен иметь к нему доступ).
    - ``None`` — режим «Все проекты» (только для super_admin; API получает NULL и агрегирует).

    Ошибки:
    - 400, если параметр не передан.
    - 403, если у staff нет доступа к проекту.
    - 404, если проект по slug не найден.
    """
    from app.core.exceptions import BadRequestError

    slug = request.headers.get("x-admin-project") or request.query_params.get("project")
    if not slug:
        raise BadRequestError(detail="Не указан X-Admin-Project / ?project=")
    slug = slug.strip().lower()

    if slug in ("__all__", "all"):
        if claims.role != "super_admin":
            raise ForbiddenError(detail="Режим «Все проекты» доступен только super_admin")
        return None

    from app.domain.tenant.project_cache import get_project_by_slug

    project = await get_project_by_slug(slug)
    if project is None:
        raise NotFoundError(detail=f"Проект '{slug}' не найден")

    if claims.role != "super_admin":
        if claims.projects is None or project.id not in claims.projects:
            raise ForbiddenError(detail="Нет доступа к этому проекту")
    return project
