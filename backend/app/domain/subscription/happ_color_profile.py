"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: #RRGGBB + альфа FF (формат Happ iOS).
_MINT = "#58D68DFF"
_MINT_SOFT = "#58D68DB3"
_TEAL = "#45B39DFF"
_TEAL_DARK = "#1A4D3AFF"
_FOREST = "#0C1814FF"
_SURFACE = "#0C100EFF"
_SURFACE_GLASS = "#0C100ECC"
_TEXT = "#E8F4ECFF"
_TEXT_MUTED = "#A8B8B0FF"
_ON_ACCENT = "#000000FF"
_VIOLET_GLOW = "#7C3AED99"
_BG_DEEP = "#020203FF"
_BG_MID = "#040806FF"
_BG_TEAL = "#0A1A14FF"

HAPP_PODOROZNIK_COLOR_PROFILE: dict[str, Any] = {
    "backgroundGradientRotationAngle": 168.0,
    "backgroundGradientColorIntensity": 1,
    "backgroundImageType": "system",
    "backgroundColors": [
        _BG_DEEP,
        _BG_MID,
        _BG_TEAL,
        _TEAL_DARK,
        _TEAL,
    ],
    "elipseColors": [
        _MINT,
        _TEAL,
        _VIOLET_GLOW,
    ],
    "buttonColor": _MINT,
    "buttonTextColor": _ON_ACCENT,
    "buttonTimerColor": _TEXT,
    "buttonImageType": "light",
    "powerIconColor": _TEAL_DARK,
    "subsHeaderColor": _TEAL_DARK,
    "subHeaderButtonColor": _TEXT,
    "subscriptionInfoBackgroundColor": _FOREST,
    "subscriptionTrafficBackgroundColor": _TEAL,
    "subscriptionInfoTextColor": _TEXT,
    "serverRowBackgroundColor": _SURFACE_GLASS,
    "selectedServerRowColor": "#2D7A5AB5",
    "serverRowTitleTextColor": _TEXT,
    "serverRowSubTitleTextColor": _TEXT_MUTED,
    "serverRowChevronColor": _MINT_SOFT,
    "disclosureHeaderTextColor": _TEXT,
    "disclosureSubHeaderTextColor": _TEXT_MUTED,
    "supportIconColor": _TEXT,
    "topBarButtonsColor": _TEXT,
    "additionalOptionsButtonColor": _TEXT,
    "profileWebPageIconColor": _MINT,
    "settingsControlsTintColor": _MINT,
}


def happ_color_profile_header_value() -> str:
    """Компактный JSON для заголовка ``color-profile`` (plain string)."""
    return json.dumps(
        HAPP_PODOROZNIK_COLOR_PROFILE,
        ensure_ascii=False,
        separators=(",", ":"),
    )
