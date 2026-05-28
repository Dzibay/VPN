"""Утилиты для дат и времени.

Хранение в БД: ``timestamptz`` / моменты — UTC. Календарное поле ``subscription_until``
(date) — **последний день доступа по календарю Москвы** (Europe/Moscow).

* Подписка, продление, Xray-клиенты, ``notify_sub_expire_*`` — ``moscow_today()`` и
  ``seconds_until_next_moscow_time``.
* Снимки трафика ``traffic_date`` и «активные за день» в daily_stats — календарный день UTC
  (``utc_today()``; не менять без миграции). Регистрации, первые оплаты и устройства в
  daily_stats — календарный день Europe/Moscow (``moscow_today()``, ``utc_instant_to_moscow_date``).
* Поля ``datetime`` в JSON API — Москва (``app.core.moscow_api_time``).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def utc_today() -> date:
    """Календарный день UTC (трафик, аналитика по UTC-дням)."""

    return datetime.now(timezone.utc).date()


def utc_now() -> datetime:
    """Timezone-aware UTC-now."""

    return datetime.now(timezone.utc)


def moscow_now() -> datetime:
    """Текущий момент в Europe/Moscow (aware)."""

    return datetime.now(MOSCOW_TZ)


def moscow_today() -> date:
    """Календарный день Europe/Moscow — граница подписки и напоминаний ``notify_sub_expire_*``."""

    return moscow_now().date()


def moscow_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """UTC-инстанты полуинтервала [start, end) для календарного дня ``d`` по Москве."""

    start_msk = datetime.combine(d, time.min, tzinfo=MOSCOW_TZ)
    end_msk = start_msk + timedelta(days=1)
    return start_msk.astimezone(timezone.utc), end_msk.astimezone(timezone.utc)


def utc_instant_to_moscow_date(dt: datetime) -> date:
    """Календарный день Europe/Moscow для момента ``timestamptz`` из БД (UTC)."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.astimezone(MOSCOW_TZ).date()


def moscow_date_period_start_utc(d: date) -> datetime:
    """Начало суток ``d`` по Москве как aware UTC — для ``period_start_utc`` в daily-stats."""

    start, _ = moscow_day_bounds_utc(d)
    return start


def seconds_until_next_moscow_time(hour: int, minute: int) -> float:
    """Секунды сна до следующего ``hour:minute`` по Europe/Moscow."""

    now = moscow_now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def seconds_until_next_local_time(hour: int, minute: int) -> float:
    """Секунды до следующего ``hour:minute`` в **локальном** TZ процесса (legacy).

    Предпочтительно ``seconds_until_next_moscow_time`` для бизнес-планировщиков.
    """

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def as_calendar_date(d_raw: object) -> date | None:
    """Привести значение из БД к ``date``: ``datetime`` → ``.date()``, ``date`` → как есть, иначе ``None``."""

    if isinstance(d_raw, datetime):
        return d_raw.date()
    if isinstance(d_raw, date):
        return d_raw
    return None
