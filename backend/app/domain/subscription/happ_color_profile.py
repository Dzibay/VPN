"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: Emerald Premium
_MINT = "#3DDC97FF"
_MINT_SOFT = "#3DDC97B3"
_TEAL = "#22C55EFF"
_TEAL_DARK = "#0B2E1FFF"
_FOREST = "#06120CFF"
_SURFACE = "#08100BFF"
_SURFACE_GLASS = "#08100BCC"
_TEXT = "#E9FFF1FF"
_TEXT_MUTED = "#92B3A0FF"
_ON_ACCENT = "#000F08FF"
_VIOLET_GLOW = "#22C55E66"
_BG_DEEP = "#000000FF"
_BG_MID = "#031009FF"
_BG_TEAL = "#072015FF"

HAPP_PODOROZNIK_COLOR_PROFILE = {
    "backgroundGradientRotationAngle": 160.0,
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
        "#16A34AFF",
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
    "subscriptionTrafficBackgroundColor": "#16A34AFF",
    "subscriptionInfoTextColor": _TEXT,
    "serverRowBackgroundColor": _SURFACE_GLASS,
    "selectedServerRowColor": "#1F9D5AB5",
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
