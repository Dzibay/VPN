"""Публичный origin для /sub/… (диплинки, бот): https для интернет-доменов."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def host_should_keep_http_for_subscription(hostname: str | None) -> bool:
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
    if host_should_keep_http_for_subscription(parsed.hostname):
        return s
    return "https://" + s[7:]
