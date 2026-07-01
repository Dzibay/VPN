from fastapi import APIRouter, Request

from app.config import settings
from app.core.client_ip import resolve_client_ip
from app.domain.models.site_public import IpBlockedStatusResponse, PublicProjectLegalInfo, PublicSiteLinksResponse
from app.domain.security.blocked_ip_cache import ensure_blocked_ips_loaded, is_ip_blocked
from app.domain.tenant.legal_profile import build_project_legal_profile
from app.domain.public_urls import (
    public_spa_base_url,
    support_telegram_public_url,
    telegram_bot_public_page_url,
)

router = APIRouter(tags=["public"])


def _legal_info_response() -> PublicProjectLegalInfo:
    profile = build_project_legal_profile(settings)
    return PublicProjectLegalInfo(
        service_name=profile.service_name,
        site_url=profile.site_url,
        domain=profile.domain,
        telegram_bot=profile.telegram_bot,
        support_telegram=profile.support_telegram,
        support_email=profile.support_email,
        operator_name=profile.operator_name,
        operator_inn=profile.operator_inn,
        dispute_jurisdiction=profile.dispute_jurisdiction,
        effective_date=profile.effective_date,
        trial_days_after_registration=profile.trial_days_after_registration,
        trial_extra_days_referral_registration=profile.trial_extra_days_referral_registration,
        trial_days_with_referral=profile.trial_days_with_referral,
        trial_traffic_limit_gib=profile.trial_traffic_limit_gib,
    )


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
        legal=_legal_info_response(),
    )


@router.get(
    "/public/project-legal",
    response_model=PublicProjectLegalInfo,
    summary="Публичные данные проекта для юридических документов",
)
async def public_project_legal() -> PublicProjectLegalInfo:
    return _legal_info_response()


@router.get(
    "/public/ip-blocked",
    response_model=IpBlockedStatusResponse,
    summary="Проверка блокировки IP (для SPA; эндпоинт не блокируется middleware)",
)
async def public_ip_blocked(request: Request) -> IpBlockedStatusResponse:
    client_ip = resolve_client_ip(request.scope)
    blocked = await ensure_blocked_ips_loaded()
    return IpBlockedStatusResponse(blocked=is_ip_blocked(client_ip, blocked))
