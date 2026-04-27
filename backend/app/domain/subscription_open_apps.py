"""
Диплинки для открытия подписки во внешних клиентах (GET /sub/{token}/open/{client}).

Шаблоны от пользователя; query-параметры url/name кодируются через quote.
Имя профиля для схем с ?name= — см. SUBSCRIPTION_IMPORT_DISPLAY_NAME.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

# Параметр name= для clashmeta, v2rayng и фрагмент #… для Shadowrocket
SUBSCRIPTION_IMPORT_DISPLAY_NAME = "Подорожник VPN"


@dataclass(frozen=True)
class SubscriptionOpenApp:
    slug: str
    display_name: str
    build_deeplink: Callable[[str], str]


def _sub_url_trim(subscription_https_url: str) -> str:
    return subscription_https_url.strip()


def _q(s: str) -> str:
    return quote(s, safe="")


def _happ_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return "happ://add/" + u.lstrip("/")


def _stash_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"stash://install-config?url={_q(u)}"


def _shadowrocket_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    name = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    return f"shadowrocket://add/{_q(u)}#{_q(name)}"


def _streisand_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return "streisand://import/" + u.lstrip("/")


def _flclashx_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"flclashx://install-config?url={_q(u)}"


def _clashmeta_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    n = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    return f"clashmeta://install-config?name={_q(n)}&url={_q(u)}"


def _v2rayng_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    n = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    return f"v2rayng://install-config?name={_q(n)}&url={_q(u)}"


def _koala_clash_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"koala-clash://install-config?url={_q(u)}"


def _prizrak_box_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"prizrak-box://install-config?url={_q(u)}"


SUBSCRIPTION_OPEN_APPS: dict[str, SubscriptionOpenApp] = {
    "happ": SubscriptionOpenApp("happ", "Happ", _happ_deeplink),
    "stash": SubscriptionOpenApp("stash", "Stash", _stash_deeplink),
    "shadowrocket": SubscriptionOpenApp(
        "shadowrocket", "Shadowrocket", _shadowrocket_deeplink
    ),
    "streisand": SubscriptionOpenApp("streisand", "Streisand", _streisand_deeplink),
    "flclashx": SubscriptionOpenApp("flclashx", "FLClashX", _flclashx_deeplink),
    "clashmeta": SubscriptionOpenApp("clashmeta", "Clash Meta", _clashmeta_deeplink),
    "v2rayng": SubscriptionOpenApp("v2rayng", "v2rayNG", _v2rayng_deeplink),
    "koala-clash": SubscriptionOpenApp(
        "koala-clash", "Koala Clash", _koala_clash_deeplink
    ),
    "prizrak-box": SubscriptionOpenApp(
        "prizrak-box", "Prizrak Box", _prizrak_box_deeplink
    ),
}


def get_subscription_open_app(client_slug: str) -> SubscriptionOpenApp | None:
    return SUBSCRIPTION_OPEN_APPS.get((client_slug or "").strip().lower())


def list_subscription_open_app_slugs() -> list[str]:
    return sorted(SUBSCRIPTION_OPEN_APPS.keys())
