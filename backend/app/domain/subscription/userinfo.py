"""Значение HTTP-заголовка ``subscription-userinfo`` для ответов подписки /sub/…

Имя заголовка в ответе API — ``subscription-userinfo`` (как в документации Happ); для клиентов
оно эквивалентно историческому ``Subscription-Userinfo`` (HTTP нечувствителен к регистру).

Формат (общий для экосистемы Clash / Mihomo и Xray-клиентов):

  ``upload=<bytes>; download=<bytes>; total=<bytes>; expire=<unix>``

- ``upload`` / ``download`` — использованный трафик по направлениям (байты).
- ``total`` — квота в байтах; ``0`` означает без лимита (см. примеры Happ).
- ``expire`` — Unix-секунды: **00:00 Europe/Moscow** на календарный день после ``valid_until``
  (конец последнего оплаченного дня по Москве).

Ссылки на документацию клиентов из ``subscription.open_apps``:

- **Happ**: https://www.happ.su/happ/dev-docs/app-management — заголовок
  ``subscription-userinfo``, параметр ``expire`` для даты окончания.
- **Stash**: https://stash.wiki/en/features/service-provider-subscription —
  ``Subscription-Userinfo`` при обновлении подписки (в т.ч. HEAD).
- **Clash Verge Rev / Mihomo-семейство** (FlClashX, Koala Clash, Prizrak Box, Clash Meta):
  заголовок ``subscription-userinfo``; см. руководства Clash Verge (profile subscription headers).
- **Shadowrocket**: тот же де-факто формат userinfo при импорте подписки.
- **v2rayNG**: поддержка метаданных подписки через заголовки (в т.ч.
  ``subscription-userinfo``); см. issues в репозитории 2dust/v2rayNG.
- **Streisand**, **v2RayTun**: совместимы с распространёнными полями подписок Xray/Clash
  при запросе того же URL.

Дата ``valid_until`` в БД — последний день доступа по календарю Москвы; в ``expire`` — полночь
следующего дня по Москве (секунды Unix).
"""

from __future__ import annotations

import base64
from datetime import date, datetime, time, timedelta

from app.core.time import MOSCOW_TZ

_HAPP_ANNOUNCE_MAX_CHARS = 200


def happ_utf8_header_value(text: str, *, max_chars: int | None = None) -> str:
    """
    UTF-8 в HTTP-заголовках подписки Happ (``profile-title``, ``announce``, …).

    Starlette кодирует заголовки как latin-1 — сырой кириллический текст и эмодзи дают
    ``UnicodeEncodeError``. Happ принимает ``base64:<Base64(UTF-8)>`` (dev-docs app-management).
    """
    if not (text or "").strip():
        return ""
    t = text.strip()
    if max_chars is not None and len(t) > max_chars:
        t = t[:max_chars]
    try:
        t.encode("latin-1")
        return t
    except UnicodeEncodeError:
        payload = base64.b64encode(t.encode("utf-8")).decode("ascii")
        return f"base64:{payload}"


def subscription_profile_title_header_value(title: str | None = None) -> str:
    """Заголовок ``profile-title`` — имя профиля подписки в Happ и совместимых клиентах."""
    from app.domain.tenant.branding import resolve_brand_name

    return happ_utf8_header_value(title if title is not None else resolve_brand_name())


def subscription_announce_header_value(text: str) -> str:
    """
    Значение для HTTP-заголовка ``announce`` (Happ и др.).

    Длина после декодирования — не более 200 символов (ограничение Happ).
    """
    return happ_utf8_header_value(text, max_chars=_HAPP_ANNOUNCE_MAX_CHARS)


def subscription_valid_until_to_expire_unix(valid_until: date | None) -> int | None:
    if valid_until is None:
        return None
    expire_moment = datetime.combine(
        valid_until + timedelta(days=1),
        time.min,
        tzinfo=MOSCOW_TZ,
    )
    return int(expire_moment.timestamp())


def build_subscription_userinfo_header_value(
    *,
    valid_until: date | None,
    upload: int = 0,
    download: int = 0,
    total: int = 0,
) -> str:
    parts = [
        f"upload={max(0, int(upload))}",
        f"download={max(0, int(download))}",
        f"total={max(0, int(total))}",
    ]
    exp = subscription_valid_until_to_expire_unix(valid_until)
    if exp is not None:
        parts.append(f"expire={exp}")
    return "; ".join(parts)
