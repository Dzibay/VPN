from fastapi import APIRouter

from app.config import settings
from app.domain.models.payments import SitePaymentTariffsResponse
from app.domain.models.site_public import PublicSiteLinksResponse
from app.domain.public_urls import support_telegram_public_url, telegram_bot_public_page_url
from app.domain.services.yookassa_service import yookassa_tariffs_public_response

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


@router.get(
    "/public/yookassa-tariffs",
    response_model=SitePaymentTariffsResponse,
    summary="Тарифы разовой оплаты на сайте (app/data/yookassa_tariffs.json)",
)
async def public_yookassa_tariffs() -> SitePaymentTariffsResponse:
    return yookassa_tariffs_public_response()
