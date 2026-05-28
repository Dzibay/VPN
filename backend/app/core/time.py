"""Утилиты для дат и времени.

Хранение в БД: ``timestamptz`` / моменты — UTC. Календарное поле ``subscription_until``
(date) — **последний день доступа по календарю Москвы** (Europe/Moscow).

* Подписка, продление, Xray-клиенты, ``notify_sub_expire_*`` — ``moscow_today()`` и
  ``seconds_until_next_moscow_time``.
* Снимки трафика ``traffic_date`` и «активные за день» в daily_stats — календарный день UTC
  (``utc_today()``; не менять без миграции). Регистрации, первые оплаты и устройства в
  daily_stats — календарный день Europe/Moscow (``moscow_today()``, ``utc_instant_to_moscow_date``).
* Поля ``datetime`` в JSON API — Москва (``app.core.moscow_api_time``); фронт не переводит TZ.
* Графики staff: ``stats_date`` / группировки — Europe/Moscow в RPC; ``traffic_date`` — UTC.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def utc_today() -> date:
    """Календарный день UTC (трафик, аналитика по UTC-дням)."""

    return utc_now().date()


def utc_now() -> datetime:
    """Timezone-aware UTC-now."""

    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Привести ``datetime`` к aware UTC (наивное считается UTC)."""

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc_z(dt: datetime) -> str:
    """ISO 8601 в UTC с суффиксом ``Z`` (для внешних API)."""

    return ensure_utc(dt).isoformat().replace("+00:00", "Z")


def iter_calendar_days(d0: date, d1: date) -> list[date]:
    """Все календарные дни от ``d0`` до ``d1`` включительно."""

    out: list[date] = []
    d = d0
    while d <= d1:
        out.append(d)
        d += timedelta(days=1)
    return out


def msk_month_bounds(month: str) -> tuple[date, date]:
    """Первый и последний календарный день месяца YYYY-MM (Europe/Moscow — тот же григорианский месяц)."""

    s = month.strip()
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError("month: ожидается формат YYYY-MM")
    try:
        y = int(parts[0], 10)
        mo = int(parts[1], 10)
    except ValueError as e:
        raise ValueError("month: неверные числа в YYYY-MM") from e
    if y < 1970 or y > 2100 or mo < 1 or mo > 12:
        raise ValueError("month: недопустимый год или месяц")
    first = date(y, mo, 1)
    last = date(y, mo, calendar.monthrange(y, mo)[1])
    return first, last


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

    return ensure_utc(dt).astimezone(MOSCOW_TZ).date()


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


def as_calendar_date(d_raw: object) -> date | None:
    """Привести значение из БД к ``date``: ``datetime`` → ``.date()``, ``date`` → как есть, иначе ``None``."""

    if isinstance(d_raw, datetime):
        return d_raw.date()
    if isinstance(d_raw, date):
        return d_raw
    return None
