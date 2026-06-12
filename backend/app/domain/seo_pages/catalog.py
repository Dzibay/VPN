"""Каталог SEO-страниц (path, title, sort_order). Должен совпадать с frontend/src/content/seo/index.js."""

from __future__ import annotations

SEO_PAGES_CATALOG: list[tuple[str, str, int]] = [
    ("/", "Главная", 1),
    ("/vpn-dlya-youtube", "VPN для YouTube", 10),
    ("/vpn-dlya-youtube/android", "VPN для YouTube на Android", 11),
    ("/vpn-dlya-youtube/pc", "VPN для YouTube на ПК", 12),
    ("/vpn-dlya-gemini", "VPN для Gemini", 20),
    ("/vpn-dlya-telegram", "VPN для Telegram", 30),
]

SEO_PAGE_PATHS: frozenset[str] = frozenset(path for path, _title, _sort in SEO_PAGES_CATALOG)
