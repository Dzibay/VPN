"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: Lime Energy
_MINT = "#CBFF6AFF"
_MINT_SOFT = "#CBFF6AB3"
_TEAL = "#A3E635FF"
_TEAL_DARK = "#2D5E1EFF"
_FOREST = "#0A1208FF"
_SURFACE = "#101608FF"
_SURFACE_GLASS = "#101608CC"
_TEXT = "#FAFFEFFF"
_TEXT_MUTED = "#C0CCAAFF"
_ON_ACCENT = "#111500FF"
_VIOLET_GLOW = "#BEF26455"
_BG_DEEP = "#060702FF"
_BG_MID = "#121A06FF"
_BG_TEAL = "#253E14FF"

HAPP_PODOROZNIK_COLOR_PROFILE = {
    "backgroundGradientRotationAngle": 165.0,
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
        "#84CC16FF",
        _VIOLET_GLOW,
    ],
    "buttonColor": _MINT,
    "buttonTextColor": _ON_ACCENT,
    "buttonTimerColor": _TEXT,
    "buttonImageType": "light",
    "powerIconColor": "#4D7C0FFF",
    "subsHeaderColor": "#4D7C0FFF",
    "subHeaderButtonColor": _TEXT,
    "subscriptionInfoBackgroundColor": _FOREST,
    "subscriptionTrafficBackgroundColor": "#84CC16FF",
    "subscriptionInfoTextColor": _TEXT,
    "serverRowBackgroundColor": _SURFACE_GLASS,
    "selectedServerRowColor": "#84CC16B5",
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
