"""
Диплинки для открытия подписки во внешних клиентах (GET /sub/{token}/open/{client}/data; UI: открытие — /sub/…/open/…, скачивание — /apps/{code}, см. GET /api/public/client-apps/{code});
список клиентов для ЛК — GET /api/auth/me (subscription_open_clients).

Метаданные срока и трафика при запросе URL подписки: заголовки Happ
(``subscription-userinfo``, ``profile-update-interval``, …) на ``GET/HEAD /sub/{token}``
(см. ``app.domain.subscription.userinfo`` и документацию Happ, Stash Wiki, Clash Verge Rev).

- happ: сырая ссылка в path — happ://add/https://…/sub/{token}
- Stash, Clash Meta, flclashx, koala-clash, prizrak-box: в query url=… указывает на
  ``GET /sub/{token}/clash`` (тело — YAML Clash Meta), не на Base64-подписку ``/sub/{token}``.
- v2rayNG: url на ``/sub/{token}`` (Base64 со строками vless://); по UrlSchemeActivity
  читаются только query url и fragment (имя), не name=.
- Shadowrocket: shadowrocket://add/sub://<base64(UTF-8 ссылки)>?remark=…
  (3x-ui / community, иначе импорт не срабатывает; не путать с urlencoding в path)
- Streisand: панели (напр. 3x-ui) — streisand://install-subscription?url=…
- v2raytun: v2raytun://import/{subscription} (сырая ссылка в path)

Имя профиля — ``app.constants.BRAND_NAME``.

Ссылки для страницы open: см. `_stores` / `_platform_ref`. Строка (URL) = только сайт/магазин;
кортеж ``(site, download)`` = отдельно страница и прямое скачивание файла.


"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeAlias
from urllib.parse import quote

from app.constants import BRAND_NAME

PlatformLinkInput: TypeAlias = str | tuple[str | None, str | None]


@dataclass(frozen=True)
class StorePlatformRefs:
    """Обязательна логика на фронте open: есть site — показывается «Перейти на сайт»; есть download — «Скачать»."""

    site: str | None = None
    download: str | None = None

    def any(self) -> bool:
        return bool(self.site or self.download)


@dataclass(frozen=True)
class AppStoreLinks:
    """Ссылки по ОС: см. ``StorePlatformRefs``."""

    windows: StorePlatformRefs | None = None
    android: StorePlatformRefs | None = None
    ios: StorePlatformRefs | None = None
    macos: StorePlatformRefs | None = None
    linux: StorePlatformRefs | None = None

    def any(self) -> bool:
        for ref in (
            self.windows,
            self.android,
            self.ios,
            self.macos,
            self.linux,
        ):
            if ref is not None and ref.any():
                return True
        return False

    def to_public_json_dict(self) -> dict[str, dict[str, str | None]]:
        """Структура для JSON на странице /sub/.../open/{client}."""
        out: dict[str, dict[str, str | None]] = {}
        for key in ("windows", "android", "ios", "macos", "linux"):
            ref = getattr(self, key)
            if isinstance(ref, StorePlatformRefs) and ref.any():
                out[key] = {"site": ref.site, "download": ref.download}
        return out


def _platform_ref(raw: PlatformLinkInput | None) -> StorePlatformRefs | None:
    """Строка — только сайт магазина/страницы. Кортеж — (site, download); можно None в одном из полей."""

    if raw is None:
        return None
    if isinstance(raw, tuple):
        a, b = raw[0], raw[1]
        site = (a or "").strip() or None
        download = (b or "").strip() or None
        if not site and not download:
            return None
        return StorePlatformRefs(site=site, download=download)
    s = raw.strip()
    if not s:
        return None
    return StorePlatformRefs(site=s, download=None)


def _stores(
    *,
    windows: PlatformLinkInput | None = None,
    android: PlatformLinkInput | None = None,
    ios: PlatformLinkInput | None = None,
    macos: PlatformLinkInput | None = None,
    linux: PlatformLinkInput | None = None,
) -> AppStoreLinks:
    """Собрать ``AppStoreLinks`` из строк (только сайт) или пар ``(site, download)``. См. ``PlatformLinkInput``."""

    return AppStoreLinks(
        windows=_platform_ref(windows),
        android=_platform_ref(android),
        ios=_platform_ref(ios),
        macos=_platform_ref(macos),
        linux=_platform_ref(linux),
    )


def store_platform_tags(links: AppStoreLinks) -> list[str]:
    """Теги для фильтра в ЛК: windows | android | ios | macos | linux. Пусто — клиент для любой платформы."""
    if not links.any():
        return []
    tags: list[str] = []
    if links.android is not None and links.android.any():
        tags.append("android")
    if links.ios is not None and links.ios.any():
        tags.append("ios")
    if links.windows is not None and links.windows.any():
        tags.append("windows")
    if links.macos is not None and links.macos.any():
        tags.append("macos")
    if links.linux is not None and links.linux.any():
        tags.append("linux")
    return tags


@dataclass(frozen=True)
class SubscriptionOpenApp:
    client_code: str
    display_name: str
    build_deeplink: Callable[[str], str]
    store_links: AppStoreLinks = field(default_factory=AppStoreLinks)
    subscription_fetch_path_suffix: str = ""


def _sub_url_trim(subscription_https_url: str) -> str:
    return subscription_https_url.strip()


def _deeplink_query_url(prefix: str) -> Callable[[str], str]:
    """prefix заканчивается на «…?url=»; subscription URL подставляется без percent-encoding."""

    def build(subscription_https_url: str) -> str:
        return prefix + _sub_url_trim(subscription_https_url)

    return build


def _q(s: str) -> str:
    return quote(s, safe="")


def _b64_utf8(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _happ_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return "happ://add/" + u.lstrip("/")


_stash_deeplink = _deeplink_query_url("stash://install-config?url=")


def _shadowrocket_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    b64 = _b64_utf8(u)
    return f"shadowrocket://add/sub://{b64}?remark={_q(BRAND_NAME)}"


_streisand_deeplink = _deeplink_query_url("streisand://install-subscription?url=")

_flclashx_deeplink = _deeplink_query_url("flclashx://install-config?url=")


def _clashmeta_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"clashmeta://install-config?url={u}&name={_q(BRAND_NAME)}"


def _v2rayng_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"v2rayng://install-sub?url={u}#{_q(BRAND_NAME)}"


def _v2raytun_deeplink(subscription_https_url: str) -> str:
    u = _sub_url_trim(subscription_https_url)
    return f"v2raytun://import/{u}"


_koala_clash_deeplink = _deeplink_query_url("koala-clash://install-config?url=")

_prizrak_box_deeplink = _deeplink_query_url("prizrak-box://install-config?url=")


_STORE: dict[str, AppStoreLinks] = {
    "happ": _stores(
        android=(
            "https://play.google.com/store/apps/details?id=com.happproxy",
            "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
        ),
        ios="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
        windows=(
            "https://github.com/Happ-proxy/happ-desktop/releases",
            "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
        ),
        macos="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
        linux="https://www.happ.su/main/ru",
    ),
    "stash": _stores(ios="https://apps.apple.com/us/app/stash-rule-based-proxy/id1596063349"),
    "shadowrocket": _stores(ios="https://apps.apple.com/ru/app/shadowrocket/id932747118"),
    "streisand": _stores(ios="https://apps.apple.com/ru/app/streisand/id6450534064"),
    "flclashx": _stores(
        android=(
            "https://github.com/pluralplay/FlClashX/releases",
            "https://github.com/pluralplay/FlClashX/releases/latest/download/FlClashX-android-universal.apk",
        ),
        windows=(
            "https://github.com/pluralplay/FlClashX/releases",
            "https://github.com/pluralplay/FlClashX/releases/latest/download/FlClashX-windows-amd64-setup.exe",
        ),
        macos=(
            "https://github.com/pluralplay/FlClashX/releases",
            "https://github.com/pluralplay/FlClashX/releases/latest/download/FlClashX-macos-arm64.dmg",
        ),
        linux=(
            "https://github.com/pluralplay/FlClashX/releases",
            "https://github.com/pluralplay/FlClashX/releases/latest/download/FlClashX-linux-amd64.deb",
        ),
    ),
    "clashmeta": _stores(
        android=(
            "https://f-droid.org/packages/com.github.metacubex.clash.meta/",
            "https://github.com/MetaCubeX/ClashMetaForAndroid/releases/download/v2.11.20/cmfa-2.11.20-meta-universal-release.apk",
        ),
        windows="https://github.com/MetaCubeX/Clash.Meta/releases",
        macos="https://github.com/MetaCubeX/Clash.Meta/releases",
        linux="https://github.com/MetaCubeX/Clash.Meta/releases",
    ),
    "v2rayng": _stores(
        android=(
            "https://github.com/2dust/v2rayNG/releases",
            "https://github.com/2dust/v2rayNG/releases/download/1.10.31/v2rayNG_1.10.31_universal.apk",
        ),
    ),
    "v2raytun": _stores(
        android="https://play.google.com/store/apps/details?id=com.v2raytun.android",
        ios="https://apps.apple.com/app/v2raytun/id6476628951",
        windows="https://v2raytun.com",
        macos="https://v2raytun.com",
        linux="https://v2raytun.com",
    ),
    "koala-clash": _stores(
        windows=(
            "https://github.com/coolcoala/clash-verge-rev-lite/releases",
            "https://github.com/coolcoala/clash-verge-rev-lite/releases/latest/download/Koala.Clash_x64-setup.exe",
        ),
        macos=(
            "https://github.com/coolcoala/clash-verge-rev-lite/releases",
            "https://github.com/coolcoala/clash-verge-rev-lite/releases/latest/download/Koala.Clash_aarch64.dmg",
        ),
        linux=(
            "https://github.com/coolcoala/clash-verge-rev-lite/releases",
            "https://github.com/coolcoala/clash-verge-rev-lite/releases/latest/download/Koala.Clash_amd64.deb",
        ),
    ),
    "prizrak-box": _stores(
        windows=(
            "https://github.com/legiz-ru/Prizrak-Box/releases",
            "https://github.com/legiz-ru/Prizrak-Box/releases/latest/download/windows-amd64.msi",
        ),
        macos=(
            "https://github.com/legiz-ru/Prizrak-Box/releases",
            "https://github.com/legiz-ru/Prizrak-Box/releases/latest/download/macos-arm64-dmg.zip",
        ),
        linux=(
            "https://github.com/legiz-ru/Prizrak-Box/releases",
            "https://github.com/legiz-ru/Prizrak-Box/releases/latest/download/linux-amd64.deb",
        ),
    ),
}


def _app(
    client_code: str,
    name: str,
    fn: Callable[[str], str],
    *,
    subscription_fetch_path_suffix: str = "",
) -> SubscriptionOpenApp:
    return SubscriptionOpenApp(
        client_code,
        name,
        fn,
        _STORE.get(client_code, AppStoreLinks()),
        subscription_fetch_path_suffix=subscription_fetch_path_suffix,
    )


SUBSCRIPTION_OPEN_APPS: dict[str, SubscriptionOpenApp] = {
    "happ": _app("happ", "Happ", _happ_deeplink),
    "stash": _app("stash", "Stash", _stash_deeplink, subscription_fetch_path_suffix="/clash"),
    "shadowrocket": _app("shadowrocket", "Shadowrocket", _shadowrocket_deeplink),
    "streisand": _app("streisand", "Streisand", _streisand_deeplink),
    "flclashx": _app(
        "flclashx", "FLClashX", _flclashx_deeplink, subscription_fetch_path_suffix="/clash"
    ),
    "clashmeta": _app(
        "clashmeta", "Clash Meta", _clashmeta_deeplink, subscription_fetch_path_suffix="/clash"
    ),
    "v2rayng": _app("v2rayng", "v2rayNG", _v2rayng_deeplink),
    "v2raytun": _app("v2raytun", "v2RayTun", _v2raytun_deeplink),
    "koala-clash": _app(
        "koala-clash", "Koala Clash", _koala_clash_deeplink, subscription_fetch_path_suffix="/clash"
    ),
    "prizrak-box": _app(
        "prizrak-box", "Prizrak Box", _prizrak_box_deeplink, subscription_fetch_path_suffix="/clash"
    ),
}


def get_subscription_open_app(client_code: str) -> SubscriptionOpenApp | None:
    return SUBSCRIPTION_OPEN_APPS.get((client_code or "").strip().lower())


def list_subscription_open_app_codes() -> list[str]:
    return list(SUBSCRIPTION_OPEN_APPS.keys())


def list_subscription_open_apps() -> list[SubscriptionOpenApp]:
    return list(SUBSCRIPTION_OPEN_APPS.values())
