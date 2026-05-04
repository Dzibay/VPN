"""Оркестрация подписки /sub: связывает доменные модули и эндпоинты.

Доменные примитивы — в ``app.domain.subscription``:

- ``build`` — VLESS URI, JSON, Base64 и Clash YAML;
- ``devices`` — отпечаток устройства, лимит, список подключений;
- ``links`` — публичный origin, ссылки и редиректы /sub/…;
- ``userinfo`` — значение HTTP-заголовка ``subscription-userinfo``;
- ``validity`` — активность подписки по календарной дате.
"""

from __future__ import annotations

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
    SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE,
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
        announce_raw = SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE
    elif not active:
        announce_raw = "Подписка истекла — продлите подписку в личном кабинете или боте."
    else:
        announce_raw = ""
    return {
        "subscription-userinfo": userinfo,
        "profile-update-interval": "2",
        "profile-title": BRAND_NAME_ASCII,
        "support-url": "",
        "profile-web-page-url": "",
        "announce": subscription_announce_header_value(announce_raw),
        "announce-url": "",
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
