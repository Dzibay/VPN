"""
Диплинки для открытия подписки во внешних клиентах (GET /sub/{token}/open/{client});
список клиентов для ЛК — GET /api/auth/me (subscription_open_clients).

- happ: сырая ссылка в path — happ://add/https://…/sub/{token}
- Stash, Clash Meta, v2rayNG (url), flclashx, koala-clash, prizrak-box: в query
  передаётся url=… (строка URL целиком, при необходимости percent-encoded)
- Shadowrocket: shadowrocket://add/sub://<base64(UTF-8 ссылки)>?remark=…
  (3x-ui / community, иначе импорт не срабатывает; не путать с urlencoding в path)
- v2rayNG: по UrlSchemeActivity читается только query url и fragment (имя), не name=
- Streisand: панели (напр. 3x-ui) — streisand://install-subscription?url=…
- v2raytun: docs.v2raytun.com — v2raytun://import/{subscription} (URL в path, percent-encoded)

Имя профиля — SUBSCRIPTION_IMPORT_DISPLAY_NAME.

Скачивание: AppStoreLinks — android, ios, windows (ПК / релизы / сайт установки).
Поле web оставлено для обратной совместимости в скриптах страницы /open/{client}.
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
    """Ссылки «Скачать»: android, ios, windows (ПК). web — устар., не использовать в новых записях."""

    windows: str | None = None
    android: str | None = None
    ios: str | None = None
    web: str | None = None

    def any(self) -> bool:
        return bool(self.windows or self.android or self.ios or self.web)


def store_platform_tags(links: AppStoreLinks) -> list[str]:
    """Теги для фильтра в ЛК: windows | android | ios. Пусто — клиент показывается для любой платформы."""
    if not links.any():
        return []
    tags: list[str] = []
    if links.android:
        tags.append("android")
    if links.ios:
        tags.append("ios")
    if links.windows or links.web:
        tags.append("windows")
    return tags


@dataclass(frozen=True)
class SubscriptionOpenApp:
    client_code: str
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


def _v2raytun_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"v2raytun://import/{_q(u)}"


def _koala_clash_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"koala-clash://install-config?url={_q(u)}"


def _prizrak_box_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"prizrak-box://install-config?url={_q(u)}"


_STORE: dict[str, AppStoreLinks] = {
    "happ": AppStoreLinks(
        android="https://play.google.com/store/apps/details?id=com.happproxy",
        ios="https://apps.apple.com/app/happ-proxy-utility/id6504287215",
        windows="https://www.happ.su/main/ru",
    ),
    "stash": AppStoreLinks(
        ios="https://apps.apple.com/app/stash-rule-based-proxy/id1596063349"
    ),
    "shadowrocket": AppStoreLinks(
        ios="https://apps.apple.com/app/shadowrocket/id932747118"
    ),
    "streisand": AppStoreLinks(
        ios="https://apps.apple.com/app/streisand/id6450534064"
    ),
    "flclashx": AppStoreLinks(
        android="https://github.com/pluralplay/FlClashX/releases"
    ),
    "clashmeta": AppStoreLinks(
        android="https://github.com/MetaCubeX/ClashMetaForAndroid/releases"
    ),
    "v2rayng": AppStoreLinks(
        android="https://play.google.com/store/apps/details?id=com.v2ray.ang"
    ),
    "v2raytun": AppStoreLinks(
        android="https://play.google.com/store/apps/details?id=com.v2raytun.android",
        ios="https://apps.apple.com/app/v2raytun/id6476628951",
        windows="https://v2raytun.com",
    ),
    "koala-clash": AppStoreLinks(
        windows="https://github.com/coolcoala/koala-clash/releases",
    ),
    "prizrak-box": AppStoreLinks(
        windows="https://github.com/legiz-ru/Prizrak-Box/releases",
    ),
}


def _app(
    client_code: str,
    name: str,
    fn: Callable[[str], str],
) -> SubscriptionOpenApp:
    return SubscriptionOpenApp(
        client_code, name, fn, _STORE.get(client_code, AppStoreLinks())
    )


SUBSCRIPTION_OPEN_APPS: dict[str, SubscriptionOpenApp] = {
    "happ": _app("happ", "Happ", _happ_deeplink),
    "stash": _app("stash", "Stash", _stash_deeplink),
    "shadowrocket": _app("shadowrocket", "Shadowrocket", _shadowrocket_deeplink),
    "streisand": _app("streisand", "Streisand", _streisand_deeplink),
    "flclashx": _app("flclashx", "FLClashX", _flclashx_deeplink),
    "clashmeta": _app("clashmeta", "Clash Meta", _clashmeta_deeplink),
    "v2rayng": _app("v2rayng", "v2rayNG", _v2rayng_deeplink),
    "v2raytun": _app("v2raytun", "v2RayTun", _v2raytun_deeplink),
    "koala-clash": _app("koala-clash", "Koala Clash", _koala_clash_deeplink),
    "prizrak-box": _app("prizrak-box", "Prizrak Box", _prizrak_box_deeplink),
}


def get_subscription_open_app(client_code: str) -> SubscriptionOpenApp | None:
    return SUBSCRIPTION_OPEN_APPS.get((client_code or "").strip().lower())


def list_subscription_open_app_codes() -> list[str]:
    return sorted(SUBSCRIPTION_OPEN_APPS.keys())


def list_subscription_open_apps() -> list[SubscriptionOpenApp]:
    return sorted(
        SUBSCRIPTION_OPEN_APPS.values(),
        key=lambda a: (a.display_name.lower(), a.client_code),
    )
