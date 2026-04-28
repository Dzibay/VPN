"""HTTP-заголовок Subscription-Userinfo для ответов подписки /sub/…

Формат (общий для экосистемы Clash / Mihomo и Xray-клиентов):

  ``upload=<bytes>; download=<bytes>; total=<bytes>; expire=<unix>``

- ``upload`` / ``download`` — использованный трафик по направлениям (байты).
- ``total`` — квота в байтах; ``0`` означает без лимита (см. примеры Happ).
- ``expire`` — время окончания в Unix **секундах** (UTC); поле опускается, если срока нет.

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

Дата ``valid_until`` в БД — календарный день **включительно**; в ``expire`` кодируем
конец этого дня 23:59:59 UTC.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone


def subscription_valid_until_to_expire_unix(valid_until: date | None) -> int | None:
    if valid_until is None:
        return None
    end_utc = datetime.combine(valid_until, time(23, 59, 59), tzinfo=timezone.utc)
    return int(end_utc.timestamp())


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
