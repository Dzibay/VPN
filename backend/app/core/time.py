"""Утилиты для дат и времени.

Все календарные операции в бэкенде должны использовать UTC: процесс может работать в любой
зоне (контейнер vs хост-машина), и без явной фиксации UTC граница «сегодня» сдвигалась бы
относительно записей в БД (registered_at, traffic_date — TIMESTAMP/DATE в UTC).
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def utc_today() -> date:
    """Календарный день UTC (источник истины для подписки и аналитики)."""

    return datetime.now(timezone.utc).date()


def utc_now() -> datetime:
    """Timezone-aware UTC-now (на случай когда нужен ``datetime``, а не ``date``)."""

    return datetime.now(timezone.utc)


def as_calendar_date(d_raw: object) -> date | None:
    """Привести значение из БД к ``date``: ``datetime`` → ``.date()``, ``date`` → как есть, иначе ``None``.

    Используется при разборе строк ``user_server_traffic.traffic_date`` и ``users.registered_at``,
    где SQLAlchemy в зависимости от типа колонки может вернуть ``datetime`` или ``date``.
    """
    if isinstance(d_raw, datetime):
        return d_raw.date()
    if isinstance(d_raw, date):
        return d_raw
    return None
