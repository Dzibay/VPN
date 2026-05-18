"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: Pine Forest
_MINT = "#8EE09BFF"
_MINT_SOFT = "#8EE09BB3"
_TEAL = "#4CAF7AFF"
_TEAL_DARK = "#1B3F31FF"
_FOREST = "#07130EFF"
_SURFACE = "#0B120EFF"
_SURFACE_GLASS = "#0B120ECC"
_TEXT = "#EDF8F0FF"
_TEXT_MUTED = "#9AB0A4FF"
_ON_ACCENT = "#021008FF"
_VIOLET_GLOW = "#4CAF7A55"
_BG_DEEP = "#07130EFF"
_BG_MID = "#102018FF"
_BG_TEAL = "#183F31FF"

HAPP_PODOROZNIK_COLOR_PROFILE = {
    "backgroundGradientRotationAngle": 172.0,
    "backgroundGradientColorIntensity": 1,
    "backgroundImageType": "system",
    "backgroundColors": [
        _BG_DEEP,
        _BG_MID,
        _BG_TEAL,
        _TEAL_DARK,
        "#2E705BFF",
    ],
    "elipseColors": [
        _MINT,
        _TEAL,
        _VIOLET_GLOW,
    ],
    "buttonColor": "#6FCF97FF",
    "buttonTextColor": _ON_ACCENT,
    "buttonTimerColor": _TEXT,
    "buttonImageType": "light",
    "powerIconColor": "#214D3BFF",
    "subsHeaderColor": "#214D3BFF",
    "subHeaderButtonColor": _TEXT,
    "subscriptionInfoBackgroundColor": _FOREST,
    "subscriptionTrafficBackgroundColor": "#2E705BFF",
    "subscriptionInfoTextColor": _TEXT,
    "serverRowBackgroundColor": _SURFACE_GLASS,
    "selectedServerRowColor": "#3A6F59B5",
    "serverRowTitleTextColor": _TEXT,
    "serverRowSubTitleTextColor": _TEXT_MUTED,
    "serverRowChevronColor": _MINT_SOFT,
    "disclosureHeaderTextColor": _TEXT,
    "disclosureSubHeaderTextColor": _TEXT_MUTED,
    "supportIconColor": _TEXT,
    "topBarButtonsColor": _TEXT,
    "additionalOptionsButtonColor": _TEXT,
    "profileWebPageIconColor": "#8EE09BFF",
    "settingsControlsTintColor": "#8EE09BFF",
}


def happ_color_profile_header_value() -> str:
    """Компактный JSON для заголовка ``color-profile`` (plain string)."""
    return json.dumps(
        HAPP_PODOROZNIK_COLOR_PROFILE,
        ensure_ascii=False,
        separators=(",", ":"),
    )
