"""Immutable snapshot проекта, который держится в request.state и в contextvars.

Immutable dataclass, чтобы можно было безопасно шарить между корутинами и логами.
Держим только те поля, которые нужны хендлерам / сервисам без дополнительного похода в БД
(id, slug, primary_domain, брендинг, ключи платежей и бота). Полное состояние проекта
можно перечитать через ORM ``Project`` при необходимости.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProjectContext:
    id: int
    slug: str
    name: str
    primary_domain: str
    extra_domains: tuple[str, ...] = field(default_factory=tuple)
    is_active: bool = True
    telegram_bot_username: str | None = None
    telegram_bot_api_secret: str | None = None
    support_telegram_username: str | None = None
    support_email: str | None = None
    tribute_api_key: str | None = None
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_return_url: str | None = None
    smtp_settings: dict[str, Any] | None = None
    referral_bonus_days_per_paid_month: int | None = None
    referral_fixed_first_payment_bonus_rub: int | None = None
    referral_bonus_policy: str | None = None
    trial_days_after_registration: int | None = None
    trial_extra_days_referral_registration: int | None = None
    trial_traffic_limit_gib: int | None = None
    trial_traffic_limit_enabled: bool | None = None
    happ_provider_id: str | None = None
    subscription_sub_expire_banner: dict[str, Any] | None = None
    subscription_sub_info_banner: dict[str, Any] | None = None
    brand: dict[str, Any] | None = None

    @property
    def brand_name(self) -> str | None:
        if not self.brand:
            return None
        v = self.brand.get("brand_name")
        return str(v).strip() if v else None


#: Кладём проект в contextvars, чтобы сервисы могли достать его без явного проброса
#: через 20 слоёв (внутри одной корутины FastAPI copy_context изолирует переменную).
_current_project: ContextVar[ProjectContext | None] = ContextVar(
    "current_project", default=None
)


def set_current_project(project: ProjectContext | None) -> object:
    """Возвращает reset-token для ``reset_current_project``."""
    return _current_project.set(project)


def reset_current_project(token: object) -> None:
    _current_project.reset(token)  # type: ignore[arg-type]


def get_current_project() -> ProjectContext | None:
    return _current_project.get()


def require_current_project() -> ProjectContext:
    project = _current_project.get()
    if project is None:
        raise LookupError(
            "Проект не резолвлен для этого запроса — "
            "используйте Depends(require_project) или явно передавайте project_id."
        )
    return project
