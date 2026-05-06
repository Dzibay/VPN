"""Представление полей ``datetime`` в JSON ответов API в часовом поясе Москвы (Europe/Moscow, UTC+3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from zoneinfo import ZoneInfo

_MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def utc_datetime_to_moscow_iso(dt: datetime) -> str:
    """Наивное время считается UTC; возвращает ISO 8601 со смещением Москвы."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.astimezone(_MOSCOW_TZ).isoformat()


def install_moscow_json_encoder() -> None:
    """Подменяет ``fastapi.encoders.jsonable_encoder``: все ``datetime`` в ответах — в Москве."""

    import fastapi.encoders as fe

    if getattr(fe.jsonable_encoder, "_moscow_api_time_installed", False):
        return

    _orig: Any = fe.jsonable_encoder

    def jsonable_encoder(obj: Any, custom_encoder: dict[Any, Any] | None = None, **kwargs: Any) -> Any:
        merged = dict(custom_encoder or ())
        if datetime not in merged:
            merged[datetime] = utc_datetime_to_moscow_iso
        return _orig(obj, custom_encoder=merged, **kwargs)

    setattr(jsonable_encoder, "_moscow_api_time_installed", True)
    fe.jsonable_encoder = jsonable_encoder
