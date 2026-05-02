"""Публичный origin для /sub/…

Нормализация URL из SITE_ADRESS: при http:// на публичном хосте поднимаем до https://
(диплинки вроде v2raytun://import/{url} на http ломаются).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def _host_should_keep_http(hostname: str | None) -> bool:
    """Локальная / приватная среда — http допустим; публичный хост — для подписки ожидаем https."""

    if not hostname:
        return True
    h = hostname.lower().rstrip(".")
    if h in ("localhost", "0.0.0.0"):
        return True
    if h.endswith(".localhost") or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return True
    except ValueError:
        pass
    return False


def prefer_https_subscription_public_base(base: str) -> str:
    """http → https для публичных хостов (диплинки вроде v2raytun://import/{url} ломаются на http:// в path)."""

    s = base.strip().rstrip("/")
    if not s.lower().startswith("http://"):
        return s
    parsed = urlparse(s)
    if _host_should_keep_http(parsed.hostname):
        return s
    return "https://" + s[7:]


def subscription_public_base_from_setting(configured: str) -> str:
    """Строка origin из настроек: strip + http→https для публичных хостов; пусто — пустая строка."""

    s = (configured or "").strip().rstrip("/")
    return prefer_https_subscription_public_base(s) if s else ""


def site_address_to_public_origin(raw: str) -> str:
    """SITE_ADRESS: полный URL или host[:port] без схемы (как во frontend/deploy)."""

    s = (raw or "").strip().rstrip("/")
    if not s:
        return ""
    lower = s.lower()
    if lower.startswith(("http://", "https://")):
        return subscription_public_base_from_setting(s)
    host_part = s.split("/")[0].strip()
    if not host_part:
        return ""
    hostname = host_part.split(":")[0]
    scheme = "http://" if _host_should_keep_http(hostname) else "https://"
    return subscription_public_base_from_setting(f"{scheme}{host_part}")
