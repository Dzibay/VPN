"""Контекст «кому принадлежит текущий HTTP-запрос» для логов и аудита.

Централизация: не размазывать разбор JWT / токена подписки по хендлерам.
- JWT: зависимость ``apply_request_subject_from_bearer_optional`` на роутере (см. api/router.py).
- Подписка /sub/…: после ``user_by_subscription_token`` выставляется ``subscription_token`` (см. ``links.py``).
- Вход и Telegram-сценарии: после успешного разрешения пользователя в доменном слое —
  ``bind_request_subject_user`` из ``auth_service``, ``telegram_auth_service``, ``telegram_service``."""
from __future__ import annotations

from contextvars import ContextVar

# Источник субъекта: как мы узнали user_id (для отладки и отчётов).
request_subject_user_id_ctx: ContextVar[int | None] = ContextVar(
    "request_subject_user_id",
    default=None,
)
request_subject_source_ctx: ContextVar[str] = ContextVar(
    "request_subject_source",
    default="anonymous",
)


def bind_request_subject_user(user_id: int | None, *, source: str) -> None:
    """Фиксируем пользователя для текущего запроса (перезаписывает предыдущее значение)."""
    request_subject_user_id_ctx.set(user_id)
    request_subject_source_ctx.set(source)


def bind_request_subject_from_subscription_user(user: object | None) -> None:
    """Если нашли пользователя по subscription token — привязать к контексту."""
    if user is None:
        return
    uid = getattr(user, "id", None)
    if isinstance(uid, int):
        bind_request_subject_user(uid, source="subscription_token")


def reset_request_subject() -> None:
    """В ASGI middleware: сброс в конце запроса (отдельный таск / следующий запрос)."""
    request_subject_user_id_ctx.set(None)
    request_subject_source_ctx.set("anonymous")


def get_request_subject() -> tuple[int | None, str]:
    return request_subject_user_id_ctx.get(), request_subject_source_ctx.get()
