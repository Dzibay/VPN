"""Резолв «текущего пользователя» по JWT-принципалу и проверки на допустимость операций."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.dependencies import BearerPrincipal
from app.core.exceptions import InternalServerError, UnauthorizedError
from app.infrastructure.persistence.models.user import User


def resolve_authenticated_user(session: Session, principal: BearerPrincipal) -> tuple[User, str]:
    """Текущий пользователь по JWT и его API-роль (``admin``/``manager``/``user``).

    Эта проверка переиспользуется ``GET /api/auth/me`` и ``POST /api/auth/me/change-password``:
    шаги одинаковые — найти пользователя по ``user_id`` из токена и убедиться в согласованности
    роли с фактической ``account_role`` в БД.
    """
    if principal.role == "admin":
        if principal.user_id is None:
            raise UnauthorizedError("Недействительный токен")
        user = session.get(User, principal.user_id)
        if user is None:
            raise UnauthorizedError("Пользователь не найден")
        if user.account_role != "admin":
            raise UnauthorizedError("Недействительный токен")
        return user, "admin"

    if principal.user_id is None:
        raise UnauthorizedError("Недействительный токен")
    user = session.get(User, principal.user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден")
    if not user.email and not user.telegram_id:
        raise InternalServerError("У записи нет ни email, ни telegram_id")

    api_role = "manager" if principal.role == "manager" else "user"
    return user, api_role


def user_can_add_credentials_from_site(user: User) -> tuple[bool, str | None]:
    """Можно ли через сайт добавить email и пароль к Telegram-аккаунту.

    Возвращает ``(True, None)`` если можно, иначе ``(False, причина)``: причина пригодна
    для прямой отдачи в ответе HTTP-ошибки.
    """
    if user.account_role == "admin":
        return False, "Недопустимо для аккаунта администратора"
    mail = getattr(user, "email", None) or ""
    if str(mail).strip():
        return False, "На этом аккаунте уже указан email. Входите через сайт с паролём."
    if user.telegram_id is None:
        return False, "На аккаунте не указан Telegram"
    return True, None
