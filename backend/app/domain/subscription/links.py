"""URL-помощники подписки: публичный origin, путь редиректа, страница open."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.request_subject import bind_request_subject_from_subscription_user
from app.domain.subscription.public_base import site_address_to_public_origin
from app.infrastructure.database.operations import table_select_one
from app.infrastructure.persistence.models.user import User

_STORE_PLATFORM_KEYS_SUB = frozenset({"windows", "android", "ios", "macos", "linux"})


def normalize_subscription_store_platform(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    return v if v in _STORE_PLATFORM_KEYS_SUB else None


def subscription_public_base_url(cfg: Settings | None = None) -> str:
    cfg = cfg or settings
    return site_address_to_public_origin(cfg.site_address)


async def user_by_subscription_token(session: AsyncSession, subscription_token: str) -> User | None:
    user = await table_select_one(session, User, filters={"token": subscription_token})
    bind_request_subject_from_subscription_user(user)
    return user
