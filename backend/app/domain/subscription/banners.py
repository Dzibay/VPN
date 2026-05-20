"""Заголовки Happ ``sub-expire`` / ``sub-info`` (расширенные объявления).

https://www.happ.su/main/ru/dev-docs/app-management — «Расширенные объявления».
"""

from __future__ import annotations

from datetime import date

from app.config import Settings, settings
from app.core.time import utc_today
from app.domain.public_urls import telegram_bot_public_page_url
from app.domain.subscription.placeholders import SubscriptionPlaceholderReason
from app.domain.subscription.userinfo import happ_utf8_header_value

_EXPIRE_WARNING_DAYS = 3
_SUB_INFO_COLORS = frozenset({"red", "blue", "green"})
_MAX_INFO_TEXT = 200
_MAX_INFO_BTN = 25
_DEFAULT_RENEW_FALLBACK = "https://t.me/Podoroznik_Support"


def subscription_expire_banner_active(valid_until: date | None) -> bool:
    """Баннер expire: ≤3 полных дней до ``valid_until`` или подписка уже истекла."""
    if valid_until is None:
        return False
    return (valid_until - utc_today()).days <= _EXPIRE_WARNING_DAYS


def renew_button_link(cfg: Settings | None = None) -> str:
    """Ссылка «Продлить»: env override или ``https://t.me/{TELEGRAM_BOT_USERNAME}``."""
    cfg = cfg or settings
    override = (cfg.subscription_sub_expire_button_link or "").strip()
    if override:
        return override
    return telegram_bot_public_page_url(cfg) or _DEFAULT_RENEW_FALLBACK


def _sub_info_headers(cfg: Settings) -> dict[str, str]:
    text = (cfg.subscription_sub_info_text or "").strip()
    if text == "0":
        return {"sub-info-text": ""}
    if not text:
        return {}
    headers: dict[str, str] = {
        "sub-info-text": happ_utf8_header_value(text, max_chars=_MAX_INFO_TEXT),
    }
    color = (cfg.subscription_sub_info_color or "blue").strip().lower()
    if color in _SUB_INFO_COLORS and color != "blue":
        headers["sub-info-color"] = color
    btn_text = (cfg.subscription_sub_info_button_text or "").strip()
    if btn_text:
        headers["sub-info-button-text"] = happ_utf8_header_value(
            btn_text,
            max_chars=_MAX_INFO_BTN,
        )
    btn_link = (cfg.subscription_sub_info_button_link or "").strip()
    if btn_link:
        headers["sub-info-button-link"] = btn_link
    return headers


_BLOCK_SUB_INFO: dict[SubscriptionPlaceholderReason, tuple[str, str]] = {
    "traffic_limit": (
        "Исчерпан лимит трафика. Продлите подписку в боте.",
        "red",
    ),
    "expired": (
        "Подписка истекла. Продлите её в боте.",
        "red",
    ),
    "device_limit": (
        "Достигнут лимит устройств. Освободите слот в боте.",
        "red",
    ),
}


def _block_sub_info_headers(reason: SubscriptionPlaceholderReason) -> dict[str, str]:
    text, color = _BLOCK_SUB_INFO[reason]
    headers: dict[str, str] = {
        "sub-info-text": happ_utf8_header_value(text, max_chars=_MAX_INFO_TEXT),
        "sub-info-color": color,
        "sub-info-button-text": happ_utf8_header_value("Продлить", max_chars=_MAX_INFO_BTN),
        "sub-info-button-link": renew_button_link(),
    }
    return headers


def build_subscription_banner_headers(
    *,
    valid_until: date | None,
    cfg: Settings | None = None,
    block_reason: SubscriptionPlaceholderReason | None = None,
) -> dict[str, str]:
    """``sub-expire`` (+ кнопка в бота); ``sub-info`` — предупреждение или текст из env."""
    cfg = cfg or settings
    if not cfg.subscription_sub_expire_enabled:
        return {"sub-expire": "0"}

    headers: dict[str, str] = {"sub-expire": "1"}
    link = renew_button_link(cfg)
    if link:
        headers["sub-expire-button-link"] = link

    if block_reason is not None:
        headers.update(_block_sub_info_headers(block_reason))
        return headers

    if subscription_expire_banner_active(valid_until):
        return headers

    headers.update(_sub_info_headers(cfg))
    return headers
