"""Тема Happ ``color-profile`` для Подорожник VPN.

Цвета согласованы с ``frontend/src/style.css`` (--brand-mint, --brand-teal, тёмный mesh).
Документация: https://www.happ.su/happ/dev-docs/app-management (Themes / color-profile).
"""

from __future__ import annotations

import json
from typing import Any

# Палитра: Emerald Premium v2
# OFF состояние теперь визуально очевидно.

_MINT = "#3DDC97FF"
_MINT_SOFT = "#3DDC97B3"

# Более холодный emerald
_TEAL = "#22C55EFF"

# Тёмный акцент для OFF-состояния
_TEAL_DARK = "#11241CFF"

# Дополнительный OFF цвет
_OFF_BUTTON = "#1A2B24FF"
_OFF_RING = "#2A3D35FF"

_FOREST = "#06120CFF"

_SURFACE = "#08100BFF"
_SURFACE_GLASS = "#08100BCC"

_TEXT = "#E9FFF1FF"
_TEXT_MUTED = "#92B3A0FF"

_ON_ACCENT = "#000F08FF"

# Glow стал мягче
_VIOLET_GLOW = "#22C55E44"

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
        "#123524FF",
    ],

    # Более мягкие эллипсы
    "elipseColors": [
        "#1F9D5AFF",
        "#14532DFF",
        _VIOLET_GLOW,
    ],

    # Кнопка теперь НЕ ядовито зелёная
    # В OFF выглядит выключенной
    "buttonColor": _OFF_BUTTON,

    "buttonTextColor": _TEXT,
    "buttonTimerColor": _TEXT,

    # Светлая иконка питания
    "buttonImageType": "light",

    # Иконка power не зелёная
    "powerIconColor": "#9FE8C3FF",

    "subsHeaderColor": _TEAL_DARK,
    "subHeaderButtonColor": _TEXT,

    "subscriptionInfoBackgroundColor": _FOREST,

    # Прогресс бар оставляем ярким
    "subscriptionTrafficBackgroundColor": "#16A34AFF",

    "subscriptionInfoTextColor": _TEXT,

    "serverRowBackgroundColor": _SURFACE_GLASS,

    # Активный сервер светится
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
