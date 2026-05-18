"""Тема Happ ``color-profile`` для Подорожник VPN.

Палитра из ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh + фиолетовое свечение).
Кнопка VPN: яркий ``buttonColor`` (ON), тёмный ``powerIconColor`` (OFF) — отдельных ключей в Happ нет.

Документация: https://www.happ.su/main/ru/dev-docs/app-management (только iOS).
"""

from __future__ import annotations

import json
from typing import Any

# --- Бренд (site style.css) ---
_MINT = "#58D68DFF"
_MINT_HOVER = "#6FE9A0FF"
_MINT_SOFT = "#58D68DB3"
_TEAL = "#45B39DFF"
_TEAL_DEEP = "#2D7A62FF"
_ON_ACCENT = "#000000FF"

# --- Текст ---
_TEXT = "#E8F4ECFF"
_TEXT_MUTED = "#A8B8B0FF"

# --- Поверхности ---
_FOREST = "#0A1410FF"
_SURFACE_GLASS = "#0C100ECC"
_HEADER = "#142820FF"

# --- Фон (mesh 168deg, как на сайте) ---
_BG_0 = "#03010AFF"
_BG_1 = "#040806FF"
_BG_2 = "#060A14FF"
_BG_3 = "#0C1814FF"
_BG_4 = "#1A3D32FF"

# --- Декоративные «облака» (mint + teal + лёгкий iris/violet) ---
_GLOW_MINT = "#58D68D66"
_GLOW_TEAL = "#45B39D99"
_GLOW_VIOLET = "#7C3AED4D"

HAPP_PODOROZNIK_COLOR_PROFILE: dict[str, Any] = {
    "backgroundGradientRotationAngle": 168.0,
    "backgroundGradientColorIntensity": 1,
    "backgroundImageType": "system",
    "backgroundColors": [
        _BG_0,
        _BG_1,
        _BG_2,
        _BG_3,
        _BG_4,
    ],
    "elipseColors": [
        _GLOW_MINT,
        _GLOW_TEAL,
        _GLOW_VIOLET,
    ],
    "buttonColor": _MINT,
    "buttonTextColor": _ON_ACCENT,
    "buttonTimerColor": _TEXT,
    "buttonImageType": "light",
    "powerIconColor": "#0A1A12FF",
    "subsHeaderColor": _HEADER,
    "subHeaderButtonColor": _TEXT,
    "subscriptionInfoBackgroundColor": _FOREST,
    "subscriptionTrafficBackgroundColor": _TEAL_DEEP,
    "subscriptionInfoTextColor": _TEXT,
    "serverRowBackgroundColor": _SURFACE_GLASS,
    "selectedServerRowColor": "#45B39D80",
    "serverRowTitleTextColor": _TEXT,
    "serverRowSubTitleTextColor": _TEXT_MUTED,
    "serverRowChevronColor": _MINT_SOFT,
    "disclosureHeaderTextColor": _TEXT,
    "disclosureSubHeaderTextColor": _TEXT_MUTED,
    "supportIconColor": _TEXT,
    "topBarButtonsColor": _TEXT,
    "additionalOptionsButtonColor": _TEXT,
    "profileWebPageIconColor": _MINT_HOVER,
    "settingsControlsTintColor": _MINT,
}


def happ_color_profile_header_value() -> str:
    """Компактный JSON для заголовка ``color-profile`` (plain string)."""
    return json.dumps(
        HAPP_PODOROZNIK_COLOR_PROFILE,
        ensure_ascii=False,
        separators=(",", ":"),
    )
