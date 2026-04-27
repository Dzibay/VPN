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

Скачивание (лендинг /sub/…/open/…): AppStoreLinks — ссылки в Play, App Store и на сайт;
в браузере выбор делается по navigator.userAgent (Android / iOS / остальное → web).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

# Параметр name/fragment для отображаемого имени подписки
SUBSCRIPTION_IMPORT_DISPLAY_NAME = "Подорожник VPN"


@dataclass(frozen=True)
class AppStoreLinks:
    """Куда вести при скачивании: Android → Play, iOS → App Store, ПК/прочее → website."""

    android: str | None = None
    ios: str | None = None
    web: str | None = None

    def any(self) -> bool:
        return bool(self.android or self.ios or self.web)


@dataclass(frozen=True)
class SubscriptionOpenApp:
    slug: str
    display_name: str
    build_deeplink: Callable[[str], str]
    # Ссылки на магазины / сайт — выбор по userAgent в HTML
    store_links: AppStoreLinks = field(default_factory=AppStoreLinks)


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


# См. AppStoreLinks: Android = Play, iOS = App Store, web = ПК / универсальная страница
_STORE: dict[str, AppStoreLinks] = {
    "happ": AppStoreLinks(
        android="https://play.google.com/store/apps/details?id=com.happproxy",
        ios="https://apps.apple.com/app/happ-proxy-utility/id6504287215",
        web="https://github.com/Happ-proxy/happ-android",
    ),
    "stash": AppStoreLinks(
        ios="https://apps.apple.com/app/stash-rule-based-proxy/id1596063349",
        web="https://stash.ws",
    ),
    "shadowrocket": AppStoreLinks(
        ios="https://apps.apple.com/app/shadowrocket/id932747118",
        web="https://apps.apple.com/app/shadowrocket/id932747118",
    ),
    "streisand": AppStoreLinks(
        ios="https://apps.apple.com/app/streisand/id6450534064",
        web="https://streisand.onl",
    ),
    "flclashx": AppStoreLinks(
        android="https://github.com/pluralplay/FlClashX/releases",
        web="https://github.com/pluralplay/FlClashX/releases",
    ),
    "clashmeta": AppStoreLinks(
        android="https://github.com/MetaCubeX/ClashMetaForAndroid/releases",
        web="https://github.com/MetaCubeX/ClashMetaForAndroid/releases",
    ),
    "v2rayng": AppStoreLinks(
        android="https://play.google.com/store/apps/details?id=com.v2ray.ang",
        web="https://github.com/2dust/v2rayNG/releases",
    ),
    "koala-clash": AppStoreLinks(
        web="https://github.com/coolcoala/koala-clash/releases",
    ),
    "prizrak-box": AppStoreLinks(
        web="https://github.com/legiz-ru/Prizrak-Box/releases",
    ),
}


def _app(
    slug: str,
    name: str,
    fn: Callable[[str], str],
) -> SubscriptionOpenApp:
    return SubscriptionOpenApp(
        slug, name, fn, _STORE.get(slug, AppStoreLinks())
    )


SUBSCRIPTION_OPEN_APPS: dict[str, SubscriptionOpenApp] = {
    "happ": _app("happ", "Happ", _happ_deeplink),
    "stash": _app("stash", "Stash", _stash_deeplink),
    "shadowrocket": _app("shadowrocket", "Shadowrocket", _shadowrocket_deeplink),
    "streisand": _app("streisand", "Streisand", _streisand_deeplink),
    "flclashx": _app("flclashx", "FLClashX", _flclashx_deeplink),
    "clashmeta": _app("clashmeta", "Clash Meta", _clashmeta_deeplink),
    "v2rayng": _app("v2rayng", "v2rayNG", _v2rayng_deeplink),
    "koala-clash": _app("koala-clash", "Koala Clash", _koala_clash_deeplink),
    "prizrak-box": _app("prizrak-box", "Prizrak Box", _prizrak_box_deeplink),
}


def get_subscription_open_app(client_slug: str) -> SubscriptionOpenApp | None:
    return SUBSCRIPTION_OPEN_APPS.get((client_slug or "").strip().lower())


def list_subscription_open_app_slugs() -> list[str]:
    return sorted(SUBSCRIPTION_OPEN_APPS.keys())
