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
from app.constants import BRAND_NAME_ASCII
from app.domain.models.subscription import SubscriptionOpenPageData, SubscriptionPayload
from app.domain.subscription.build import (
    build_subscription_payload,
    subscription_servers_from_db,
)
from app.domain.subscription.devices import (
    register_or_touch_subscription_device,
)
from app.domain.subscription.links import (
    normalize_subscription_store_platform,
    subscription_public_base_url,
)
from app.domain.subscription.open_apps import AppStoreLinks
from app.domain.subscription.userinfo import (
    build_subscription_userinfo_header_value,
    subscription_announce_header_value,
)
from app.domain.subscription.validity import user_has_active_subscription
from app.domain.user_traffic import user_traffic_totals
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription_service")


ANNOUNCE_RAW = "Нужна помощь? Поддержка всегда на связи"
ANNOUNCE_RAW_DEVICE_LIMIT_REJECTED = "Достигнуто максимальное количество подключений (устройств). Освободите слот в личном кабинете или обратитесь в поддержку."
ANNOUNCE_RAW_SUBSCRIPTION_EXPIRED = "Подписка истекла — продлите подписку в личном кабинете или боте"


def _routing_profile_happ(cfg: Settings | None = None) -> dict[str, object]:
    cfg = cfg or settings
    if not cfg.cascade_ru_split_routing:
        return {}
    base = subscription_public_base_url().rstrip("/")
    return {
        "Name": "Pdoroznik-RU-Direct",
        "GlobalProxy": "true",
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoH",
        "DomesticDNSDomain": "https://dns.google/dns-query",
        "DomesticDNSIP": "8.8.8.8",
        "Geoipurl": f"{base}/sub/geoip.dat",
        "Geositeurl": f"{base}/sub/geosite.dat",
        "DnsHosts": {
            "cloudflare-dns.com": "1.1.1.1",
            "dns.google": "8.8.8.8",
        },
        # Без geosite:ru: в части geosite.dat нет секции RU → Happ/Xray падают при старте.
        # Как на входном Xray: geosite:private + TLD regexp + geoip:ru (см. install_xray_on_remote.sh).
        "DirectSites": [
            "geosite:private",
            "regexp:.*\\.ru$",
            "regexp:.*\\.su$",
            "regexp:.*\\.xn--p1ai$",
        ],
        "DirectIp": [
            "geoip:private",
            "geoip:ru",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "169.254.0.0/16",
            "224.0.0.0/4",
            "255.255.255.255",
        ],
        "ProxySites": [],
        "ProxyIp": [],
        "BlockSites": [],
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


def _v2raytun_routing_header_value(cfg: Settings | None = None) -> str:
    cfg = cfg or settings
    if not cfg.cascade_ru_split_routing:
        return ""
    routing = {
        "name": "Pdoroznik RU Direct",
        "domainStrategy": "IPIfNonMatch",
        "domainMatcher": "hybrid",
        "rules": [
            {
                "type": "field",
                "outboundTag": "direct",
                "domain": [
                    "geosite:private",
                    "regexp:.*\\.ru$",
                    "regexp:.*\\.su$",
                    "regexp:.*\\.xn--p1ai$",
                ],
                "ip": ["geoip:ru", "geoip:private"],
            }
        ],
    }
    raw = json.dumps(routing, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")

async def subscription_payload_rows_for_resolved_user(
    session: AsyncSession,
    user: User,
    *,
    device_allowed: bool = True,
) -> tuple[SubscriptionPayload, User, list[Server]]:
    if not user_has_active_subscription(user):
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=False,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    if not device_allowed:
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=True,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    rows = await subscription_servers_from_db(session)
    return build_subscription_payload(user, rows), user, rows


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
) -> dict[str, str]:
    up_b, down_b, _ = await user_traffic_totals(session, int(user.id))
    userinfo = build_subscription_userinfo_header_value(
        valid_until=user.subscription_until,
        upload=up_b,
        download=down_b,
        total=0,
    )
    active = user_has_active_subscription(user)
    if device_limit_rejected and active:
        announce_raw = ANNOUNCE_RAW_DEVICE_LIMIT_REJECTED
    elif not active:
        announce_raw = ANNOUNCE_RAW_SUBSCRIPTION_EXPIRED
    else:
        announce_raw = ANNOUNCE_RAW
    ua = ((request.headers.get("user-agent") or "") if request is not None else "").lower()
    routing_header = _v2raytun_routing_header_value() if "v2raytun" in ua else _happ_routing_header_value()
    return {
        "subscription-userinfo": userinfo,
        "profile-update-interval": "1",
        "profile-title": BRAND_NAME_ASCII,
        "support-url": "https://t.me/Podoroznik_Support",
        "profile-web-page-url": "https://cool-vpn.ru",
        "announce": subscription_announce_header_value(announce_raw),
        "announce-url": "https://t.me/Podoroznik_Support",
        "routing": routing_header,
    }


def subscription_build_open_page_data(
    user: User | None,
    app,
    *,
    store_platform: str | None,
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
        return SubscriptionOpenPageData(
            state="invalid_token",
            title="Ссылка недействительна",
            headline="Ссылка недействительна",
            message="Проверьте ссылку или получите новую в боте / личном кабинете.",
            deeplink=None,
            open_button_label="",
            lead=None,
            hint=None,
            store_links=None,
            forced_platform=forced,
        )

    base = subscription_public_base_url()
    suffix = (app.subscription_fetch_path_suffix or "").strip()
    subscription_url = f"{base}/sub/{user.token}{suffix}"
    deeplink = app.build_deeplink(subscription_url)
    sl: AppStoreLinks = app.store_links
    store_json = sl.to_public_json_dict() if sl.any() else None

    active = user_has_active_subscription(user)
    lead_active = lead
    lead_inactive = (
        "Подписка сейчас не активна — узлы VPN в клиенте появятся после продления. "
        "Приложение можно открыть и заранее добавить ссылку подписки — список серверов будет пустым, пока подписка не станет активной."
    )

    return SubscriptionOpenPageData(
        state="ok",
        title=title,
        headline=headline,
        message=None,
        deeplink=deeplink,
        open_button_label=open_label,
        lead=lead_active if active else lead_inactive,
        hint=hint,
        store_links=store_json,
        forced_platform=forced,
    )
