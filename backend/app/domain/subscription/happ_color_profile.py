"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: Mint Glow
_MINT = "#7CF0ABFF"
_MINT_SOFT = "#7CF0ABB3"
_TEAL = "#5BD68DFF"
_TEAL_DARK = "#0F3A29FF"
_FOREST = "#08140FFF"
_SURFACE = "#0A0F0CFF"
_SURFACE_GLASS = "#0A0F0CCC"
_TEXT = "#F1FFF6FF"
_TEXT_MUTED = "#A7C4B3FF"
_ON_ACCENT = "#00150AFF"
_VIOLET_GLOW = "#7C3AED88"
_BG_DEEP = "#010302FF"
_BG_MID = "#041009FF"
_BG_TEAL = "#0B2117FF"

HAPP_PODOROZNIK_COLOR_PROFILE = {
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
    "selectedServerRowColor": "#39A76CB5",
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
