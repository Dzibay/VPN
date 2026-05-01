"""Значение HTTP-заголовка ``subscription-userinfo`` для ответов подписки /sub/…

Имя заголовка в ответе API — ``subscription-userinfo`` (как в документации Happ); для клиентов
оно эквивалентно историческому ``Subscription-Userinfo`` (HTTP нечувствителен к регистру).

Формат (общий для экосистемы Clash / Mihomo и Xray-клиентов):

  ``upload=<bytes>; download=<bytes>; total=<bytes>; expire=<unix>``

- ``upload`` / ``download`` — использованный трафик по направлениям (байты).
- ``total`` — квота в байтах; ``0`` означает без лимита (см. примеры Happ).
- ``expire`` — Unix **секунды** (UTC): полночь календарного дня ``valid_until`` минус **3 часа**
  (сдвиг для отображения в MSK и др.).

Ссылки на документацию клиентов из ``subscription_open_apps``:

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

Дата ``valid_until`` в БД — календарный день; в ``expire`` — момент ``00:00 UTC`` этого дня,
с минус 3 ч (секунды Unix).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def subscription_valid_until_to_expire_unix(valid_until: date | None) -> int | None:
    if valid_until is None:
        return None
    day_start_utc = datetime.combine(valid_until, time.min, tzinfo=timezone.utc)
    expire_moment = day_start_utc - timedelta(hours=3)
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
