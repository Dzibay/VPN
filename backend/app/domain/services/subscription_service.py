"""Оркестрация подписки /sub: связывает доменные модули и эндпоинты.

Доменные примитивы — в ``app.domain.subscription``:

- ``build`` — VLESS URI, JSON, Base64 и Clash YAML;
- ``devices`` — отпечаток устройства, лимит, список подключений;
- ``links`` — публичный origin, ссылки и редиректы /sub/…;
- ``userinfo`` — значение HTTP-заголовка ``subscription-userinfo``;
- ``validity`` — активность подписки по календарной дате.
"""

from __future__ import annotations

import base64
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import Settings, settings
from app.domain.public_urls import public_spa_base_url, support_telegram_public_url
from app.domain.models.subscription import SubscriptionOpenPageData, SubscriptionPayload
from app.domain.subscription.build import (
    build_subscription_payload,
    subscription_servers_from_db,
)
from app.domain.subscription.client_ua import subscription_user_agent_is_happ
from app.domain.subscription.placeholders import (
    SubscriptionPlaceholderReason,
    build_subscription_placeholder_payload,
)
from app.domain.subscription.devices import (
    register_or_touch_subscription_device,
)
from app.domain.subscription.happ_color_profile import happ_color_profile_header_value
from app.domain.subscription.links import (
    normalize_subscription_store_platform,
    subscription_public_base_url,
)
from app.domain.subscription.open_apps import AppStoreLinks
from app.domain.subscription.banners import (
    build_subscription_banner_headers,
    renew_button_link,
    subscription_expire_banner_active,
)
from app.domain.subscription.userinfo import (
    build_subscription_userinfo_header_value,
    subscription_announce_header_value,
    subscription_profile_title_header_value,
)
from app.domain.subscription.traffic_limit import user_traffic_quota_exceeded
from app.domain.subscription.validity import (
    subscription_calendar_active,
    user_has_active_subscription,
)
from app.domain.user_traffic import user_traffic_totals
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription_service")


ANNOUNCE_RAW = "⚠️ При возникновении проблем попробуйте 🔁 обновить конфигурацию. Если проблема сохраняется — обратитесь в поддержку"
ANNOUNCE_RAW_DEVICE_LIMIT_REJECTED = "Достигнуто максимальное количество подключений (устройств). Освободите слот в личном кабинете или обратитесь в поддержку."
ANNOUNCE_RAW_SUBSCRIPTION_EXPIRED = "Подписка истекла — продлите подписку в личном кабинете или боте"
ANNOUNCE_RAW_TRAFFIC_LIMIT = (
    "Исчерпан лимит трафика — продлите подписку в личном кабинете или боте"
)
_DIRECT_SERVICE_PORTS = "22,25,135-139,465,587,593,2525,3306,3389,5432,6379,11211,1900"


def _routing_profile_happ(cfg: Settings | None = None) -> dict[str, object]:
    cfg = cfg or settings
    if not cfg.cascade_ru_split_routing:
        return {}
    base = subscription_public_base_url().rstrip("/")
    return {
        "Name": "Pdoroznik-Default",
        "GlobalProxy": "true",
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://1.1.1.1/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoH",
        "DomesticDNSDomain": "https://dns.google/dns-query",
        "DomesticDNSIP": "8.8.8.8",
        "Geoipurl": f"{base}/sub/geoip.dat",
        "Geositeurl": f"{base}/sub/geosite.dat",
        "DnsHosts": {
            "1.1.1.1": "1.1.1.1",
            "8.8.8.8": "8.8.8.8",
            "domain:googleapis.cn": "googleapis.com",
            "cloudflare-dns.com": "1.1.1.1",
            "dns.google": "8.8.8.8",
        },
        "DirectSites": [
            "geosite:private",
            "geosite:category-direct",
        ],
        "DirectIp": [
            "geoip:private",
        ],
        "DirectPorts": _DIRECT_SERVICE_PORTS,
        "ProxySites": ["geosite:category-proxy"],
        "ProxyIp": [],
        "BlockSites": ["geosite:category-block"],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": "false",
    }


def _happ_routing_header_value(cfg: Settings | None = None) -> str:
    profile = _routing_profile_happ(cfg)
    if not profile:
        return ""
    raw = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload = base64.b64encode(raw).decode("ascii")
    return f"happ://routing/onadd/{payload}"


async def resolve_subscription_delivery_block(
    session: AsyncSession,
    user: User,
    *,
    device_allowed: bool,
    traffic_total_bytes: int | None = None,
) -> tuple[int, SubscriptionPlaceholderReason | None]:
    """
    Единая проверка блокировки выдачи подписки (порядок как в ``subscription_payload_rows``).

    Возвращает ``(суммарный трафик, причина заглушки или None)``.
    """
    total = traffic_total_bytes
    if user.traffic_limit_bytes is not None:
        if total is None:
            _, _, total = await user_traffic_totals(session, int(user.id))
        if user_traffic_quota_exceeded(user, used_bytes=int(total or 0)):
            return int(total or 0), "traffic_limit"
    if not subscription_calendar_active(user):
        if total is None:
            _, _, total = await user_traffic_totals(session, int(user.id))
        return int(total or 0), "expired"
    if not device_allowed:
        if total is None:
            _, _, total = await user_traffic_totals(session, int(user.id))
        return int(total or 0), "device_limit"
    if total is None:
        _, _, total = await user_traffic_totals(session, int(user.id))
    return int(total or 0), None


def _subscription_announce_raw(
    *,
    block_reason: SubscriptionPlaceholderReason | None,
    device_limit_rejected: bool,
    calendar_active: bool,
    expire_banner_active: bool,
) -> str:
    if block_reason == "traffic_limit":
        return ANNOUNCE_RAW_TRAFFIC_LIMIT
    if block_reason == "expired":
        return ANNOUNCE_RAW_SUBSCRIPTION_EXPIRED
    if block_reason == "device_limit":
        return ANNOUNCE_RAW_DEVICE_LIMIT_REJECTED
    if device_limit_rejected and calendar_active:
        return ANNOUNCE_RAW_DEVICE_LIMIT_REJECTED
    if not calendar_active and not expire_banner_active:
        return ANNOUNCE_RAW_SUBSCRIPTION_EXPIRED
    return ANNOUNCE_RAW


def _subscription_announce_url(
    *,
    block_reason: SubscriptionPlaceholderReason | None,
    expire_banner_active: bool,
    calendar_active: bool,
    cfg: Settings,
) -> str:
    if block_reason is not None or expire_banner_active or not calendar_active:
        return renew_button_link(cfg)
    return support_telegram_public_url(cfg) or renew_button_link(cfg)


def _happ_advanced_subscription_headers(cfg: Settings | None = None) -> dict[str, str]:
    """Расширенные параметры Happ; требуют ``providerid`` (``HAPP_PROVIDER_ID``)."""
    cfg = cfg or settings
    provider_id = (cfg.happ_provider_id or "").strip()
    if not provider_id:
        return {}
    return {
        "providerid": provider_id,
        "color-profile": happ_color_profile_header_value(),
        "hide-settings": "1",
        "subscription-ping-onopen-enabled": "1",
        "subscription-pin": "1",
        "manual-block-user-agent": "1",
        "ping-result": "time",
        "subscriptions-expand-now": "1",
    }


async def subscription_payload_rows_for_resolved_user(
    session: AsyncSession,
    user: User,
    *,
    device_allowed: bool = True,
    happ_json: bool = False,
    traffic_total_bytes: int | None = None,
    block_reason: SubscriptionPlaceholderReason | None = None,
) -> tuple[SubscriptionPayload, User, list[Server], SubscriptionPlaceholderReason | None]:
    if block_reason is not None:
        reason = block_reason
    else:
        _, reason = await resolve_subscription_delivery_block(
            session,
            user,
            device_allowed=device_allowed,
            traffic_total_bytes=traffic_total_bytes,
        )
    if reason is not None:
        return (
            build_subscription_placeholder_payload(user, reason=reason, happ_json=happ_json),
            user,
            [],
            reason,
        )

    rows = await subscription_servers_from_db(session)
    return (
        build_subscription_payload(user, rows, happ_json=happ_json),
        user,
        rows,
        None,
    )


async def subscription_maybe_register_device(
    *,
    session: AsyncSession,
    request: Request,
    user: User | None,
    cfg: Settings | None = None,
) -> bool:
    cfg = cfg or settings
    if user is None:
        return True
    return await register_or_touch_subscription_device(
        session,
        settings=cfg,
        user=user,
        request=request,
    )


async def subscription_client_metadata_headers(
    session: AsyncSession,
    user: User,
    *,
    request: Request | None = None,
    device_limit_rejected: bool = False,
    include_happ_routing: bool = True,
    traffic_up_bytes: int | None = None,
    traffic_down_bytes: int | None = None,
    traffic_total_bytes: int | None = None,
    block_reason: SubscriptionPlaceholderReason | None = None,
) -> dict[str, str]:
    if block_reason is not None:
        reason = block_reason
    else:
        _, reason = await resolve_subscription_delivery_block(
            session,
            user,
            device_allowed=not device_limit_rejected,
            traffic_total_bytes=traffic_total_bytes,
        )
    if traffic_total_bytes is not None:
        up_b = int(traffic_up_bytes or 0)
        down_b = int(traffic_down_bytes or 0)
        total_b = int(traffic_total_bytes)
    else:
        up_b, down_b, total_b = await user_traffic_totals(session, int(user.id))
    quota_total = int(user.traffic_limit_bytes) if user.traffic_limit_bytes is not None else 0
    userinfo = build_subscription_userinfo_header_value(
        valid_until=user.subscription_until,
        upload=up_b,
        download=down_b,
        total=quota_total,
    )
    calendar_active = subscription_calendar_active(user)
    expire_banner_active = (
        settings.subscription_sub_expire_enabled
        and subscription_expire_banner_active(user.subscription_until)
    )
    announce_raw = _subscription_announce_raw(
        block_reason=reason,
        device_limit_rejected=device_limit_rejected,
        calendar_active=calendar_active,
        expire_banner_active=expire_banner_active,
    )
    routing_header = (
        _happ_routing_header_value()
        if include_happ_routing and subscription_user_agent_is_happ(request)
        else ""
    )
    headers: dict[str, str] = {
        "subscription-userinfo": userinfo,
        "profile-update-interval": "1",
        "profile-title": subscription_profile_title_header_value(),
        **(
            {"support-url": url}
            if (url := support_telegram_public_url(settings))
            else {}
        ),
        **(
            {"profile-web-page-url": spa_url}
            if (spa_url := public_spa_base_url(settings))
            else {}
        ),
        "announce": subscription_announce_header_value(announce_raw),
        "announce-url": _subscription_announce_url(
            block_reason=reason,
            expire_banner_active=expire_banner_active,
            calendar_active=calendar_active,
            cfg=settings,
        ),
        **_happ_advanced_subscription_headers(),
        **build_subscription_banner_headers(
            valid_until=user.subscription_until,
            cfg=settings,
            block_reason=reason,
        ),
    }
    if routing_header:
        headers["routing"] = routing_header
    return headers


def subscription_build_open_page_data(
    user: User | None,
    app,
    *,
    store_platform: str | None,
    traffic_total_bytes: int = 0,
) -> SubscriptionOpenPageData:
    forced = normalize_subscription_store_platform(store_platform)
    title = f"Подключение — {app.display_name}"
    headline = title
    open_label = f"Открыть в {app.display_name}"
    lead = (
        "Один раз пробуем открыть приложение, если оно уже установлено. "
        "Если приложение не установлено - нажмите кнопку Скачать или перейдите на сайт приложения"
    )
    hint = "Если приложение не открылось, но установлено - нажмите «Открыть». "

    if user is None:
        sl_bad: AppStoreLinks = app.store_links
        store_bad = sl_bad.to_public_json_dict() if sl_bad.any() else None
        return SubscriptionOpenPageData(
            state="invalid_token",
            title="Ссылка недействительна",
            display_name=app.display_name,
            headline="Ссылка недействительна",
            message="Проверьте ссылку или получите новую в боте / личном кабинете.",
            deeplink=None,
            subscription_url=None,
            open_button_label="",
            lead=None,
            hint=None,
            store_links=store_bad,
            forced_platform=forced,
        )

    base = subscription_public_base_url()
    suffix = (app.subscription_fetch_path_suffix or "").strip()
    subscription_url = f"{base}/sub/{user.token}{suffix}"
    deeplink = app.build_deeplink(subscription_url)
    sl: AppStoreLinks = app.store_links
    store_json = sl.to_public_json_dict() if sl.any() else None

    active = (
        user_has_active_subscription(user, used_bytes=traffic_total_bytes)
        if user is not None
        else False
    )
    lead_active = lead
    lead_inactive = (
        "Подписка сейчас не активна — узлы VPN в клиенте появятся после продления. "
        "Приложение можно открыть и заранее добавить ссылку подписки — список серверов будет пустым, пока подписка не станет активной."
    )

    return SubscriptionOpenPageData(
        state="ok",
        title=title,
        display_name=app.display_name,
        headline=headline,
        message=None,
        deeplink=deeplink,
        subscription_url=subscription_url,
        open_button_label=open_label,
        lead=lead_active if active else lead_inactive,
        hint=hint,
        store_links=store_json,
        forced_platform=forced,
    )
