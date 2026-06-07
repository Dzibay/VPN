from fastapi import APIRouter

from app.config import settings
from app.domain.models.site_public import PublicSiteLinksResponse
from app.domain.public_urls import support_telegram_public_url, telegram_bot_public_page_url

router = APIRouter(tags=["public"])


@router.get(
    "/public/site-links",
    response_model=PublicSiteLinksResponse,
    summary="Публичные ссылки: бот и поддержка в Telegram",
)
async def public_site_links() -> PublicSiteLinksResponse:
    return PublicSiteLinksResponse(
        telegram_bot_page_url=telegram_bot_public_page_url(settings),
        support_telegram_url=support_telegram_public_url(settings),
    )
