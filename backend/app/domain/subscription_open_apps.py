"""
Диплинки для открытия подписки во внешних клиентах (GET /sub/{token}/open/{client}).

- happ: сырая ссылка в path — happ://add/https://…/sub/{token}
- Stash, Clash Meta, v2rayNG (url), flclashx, koala-clash, prizrak-box: в query
  передаётся url=… (строка URL целиком, при необходимости percent-encoded)
- Shadowrocket: shadowrocket://add/sub://<base64(UTF-8 ссылки)>?remark=…
  (3x-ui / community, иначе импорт не срабатывает; не путать с urlencoding в path)
- v2rayNG: по UrlSchemeActivity читается только query url и fragment (имя), не name=
- Streisand: панели (напр. 3x-ui) — streisand://install-subscription?url=…

Имя профиля — SUBSCRIPTION_IMPORT_DISPLAY_NAME.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

# Параметр name/fragment для отображаемого имени подписки
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


def _b64_utf8(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _happ_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return "happ://add/" + u.lstrip("/")


def _stash_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"stash://install-config?url={_q(u)}"


def _shadowrocket_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    name = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    b64 = _b64_utf8(u)
    return f"shadowrocket://add/sub://{b64}?remark={_q(name)}"


def _streisand_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"streisand://install-subscription?url={_q(u)}"


def _flclashx_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"flclashx://install-config?url={_q(u)}"


def _clashmeta_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    n = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    return f"clashmeta://install-config?url={_q(u)}&name={_q(n)}"


def _v2rayng_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    n = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    return f"v2rayng://install-sub?url={_q(u)}#{_q(n)}"


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
