"""Информационные заглушки в списке серверов подписки (Happ JSON, Base64, Clash)."""

from __future__ import annotations

from typing import Any, Literal

import yaml

from app.config import Settings, settings
from app.constants import BRAND_NAME
from app.domain.models.subscription import SubscriptionPayload
from app.domain.public_urls import _telegram_bot_username_clean
from app.domain.subscription.happ_subscription_encode import encode_happ_subscription_body
from app.infrastructure.persistence.models.user import User

SubscriptionPlaceholderReason = Literal["expired", "device_limit"]


def subscription_placeholder_remarks(
    reason: SubscriptionPlaceholderReason,
    *,
    cfg: Settings | None = None,
) -> list[str]:
    cfg = cfg or settings
    bot = _telegram_bot_username_clean(cfg) or "bot"
    bot_line = f"tg: @{bot}"
    if reason == "expired":
        return [
            "🚨 Подписка истекла",
            "Продлите ее в боте",
            bot_line,
        ]
    return [
        "🚨 Достигнут лимит устройств",
        "Освободите слот в боте",
        bot_line,
    ]


def build_happ_info_placeholder_profile(remark: str) -> dict[str, Any]:
    """Профиль Happ без рабочего прокси — только название в списке узлов."""
    return {
        "remarks": remark,
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True, "auth": "noauth"},
            },
        ],
        "outbounds": [
            {"tag": "block", "protocol": "blackhole"},
            {"tag": "direct", "protocol": "freedom"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "network": "tcp,udp", "outboundTag": "block"},
            ],
        },
    }


def _placeholder_servers_metadata(
    remarks: list[str],
    *,
    reason: SubscriptionPlaceholderReason,
) -> list[dict[str, Any]]:
    return [
        {
            "id": -(index + 1),
            "name": remark,
            "protocol": "info",
            "placeholder": True,
            "placeholder_reason": reason,
        }
        for index, remark in enumerate(remarks)
    ]


def build_subscription_placeholder_payload(
    user: User,
    *,
    reason: SubscriptionPlaceholderReason,
    cfg: Settings | None = None,
) -> SubscriptionPayload:
    """Тело подписки с тремя информационными JSON-профилями вместо узлов VPN."""
    cfg = cfg or settings
    remarks = subscription_placeholder_remarks(reason, cfg=cfg)
    profiles = [build_happ_info_placeholder_profile(remark) for remark in remarks]
    body, media_type = encode_happ_subscription_body(
        fmt="json_array_raw",
        json_profiles=profiles,
    )
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=reason != "expired",
        servers=_placeholder_servers_metadata(remarks, reason=reason),
        vless_uris=remarks,
        subscription_base64=body,
        subscription_media_type=media_type,
    )


def build_clash_subscription_placeholder_yaml(
    reason: SubscriptionPlaceholderReason,
    *,
    cfg: Settings | None = None,
) -> str:
    """Clash Meta: три строки direct с текстом заглушки (без реального прокси)."""
    cfg = cfg or settings
    remarks = subscription_placeholder_remarks(reason, cfg=cfg)
    proxies = [{"name": remark, "type": "direct", "udp": True} for remark in remarks]
    doc: dict[str, Any] = {
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": BRAND_NAME,
                "type": "select",
                "proxies": list(remarks),
            }
        ],
        "rules": [f"MATCH,{BRAND_NAME}"],
    }
    return yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
