from fastapi import APIRouter, Request

from app.config import settings
from app.core.client_ip import resolve_client_ip
from app.domain.models.site_public import IpBlockedStatusResponse, PublicSiteLinksResponse
from app.domain.security.blocked_ip_cache import ensure_blocked_ips_loaded, is_ip_blocked
from app.domain.public_urls import (
    public_spa_base_url,
    support_telegram_public_url,
    telegram_bot_public_page_url,
)

router = APIRouter(tags=["public"])


@router.get(
    "/public/site-links",
    response_model=PublicSiteLinksResponse,
    summary="Публичные ссылки: бот и поддержка в Telegram",
)
async def public_site_links() -> PublicSiteLinksResponse:
    return PublicSiteLinksResponse(
        canonical_site_url=public_spa_base_url(settings),
        telegram_bot_page_url=telegram_bot_public_page_url(settings),
        support_telegram_url=support_telegram_public_url(settings),
    )


@router.get(
    "/public/ip-blocked",
    response_model=IpBlockedStatusResponse,
    summary="Проверка блокировки IP (для SPA; эндпоинт не блокируется middleware)",
)
async def public_ip_blocked(request: Request) -> IpBlockedStatusResponse:
    client_ip = resolve_client_ip(request.scope)
    blocked = await ensure_blocked_ips_loaded()
    return IpBlockedStatusResponse(blocked=is_ip_blocked(client_ip, blocked))
