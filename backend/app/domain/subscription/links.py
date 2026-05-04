"""URL-помощники подписки: публичный origin, путь редиректа, страница open."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import URL as StarletteURL
from starlette.requests import Request

from app.config import Settings, settings
from app.domain.subscription.public_base import site_address_to_public_origin
from app.infrastructure.database.operations import table_select_one
from app.infrastructure.persistence.models.user import User

_STORE_PLATFORM_KEYS_SUB = frozenset({"windows", "android", "ios", "macos", "linux"})


def normalize_subscription_store_platform(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    return v if v in _STORE_PLATFORM_KEYS_SUB else None


def subscription_cabinet_redirect_url(
    cfg: Settings | None = None,
    *,
    extra_query: dict[str, str] | None = None,
) -> str:
    cfg = cfg or settings
    raw = (cfg.public_cabinet_url or "").strip().rstrip("/")
    if not raw:
        path = "/cabinet"
    elif raw.startswith(("http://", "https://")):
        path = raw
    else:
        path = raw if raw.startswith("/") else f"/{raw}"
    if extra_query:
        q = urlencode(extra_query)
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}{q}"
    return path


def subscription_public_base_url(cfg: Settings | None = None) -> str:
    cfg = cfg or settings
    return site_address_to_public_origin(cfg.site_address)


async def user_by_subscription_token(session: AsyncSession, subscription_token: str) -> User | None:
    return await table_select_one(session, User, filters={"token": subscription_token})


def subscription_open_spa_url(
    subscription_token: str,
    client: str,
    *,
    platform: str | None,
    cfg: Settings | None = None,
) -> str:
    cfg = cfg or settings
    base = subscription_public_base_url(cfg)
    t = quote(subscription_token, safe="")
    c = quote(client, safe="")
    path = f"{base}/sub/{t}/open/{c}"
    norm = normalize_subscription_store_platform(platform)
    if norm:
        return f"{path}?{urlencode({'platform': norm})}"
    return path


def subscription_open_redirect_would_loop(request: Request, redirect_url: str) -> bool:
    try:
        target = StarletteURL(redirect_url)
        cur = request.url
    except Exception:
        return False
    return (
        target.scheme == cur.scheme
        and target.netloc == cur.netloc
        and target.path == cur.path
        and str(target.query) == str(cur.query)
    )
