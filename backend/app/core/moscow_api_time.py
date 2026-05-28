"""Представление полей ``datetime`` в JSON ответов API в часовом поясе Москвы (Europe/Moscow).

Календарные поля ``date`` (например ``subscription_until``) в JSON — как в БД (YYYY-MM-DD);
смысл дня — Europe/Moscow (см. ``app.core.time.moscow_today``). Моменты ``registered_at``,
``created_at`` — UTC в БД, в ответе — ISO с offset Москвы.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.time import MOSCOW_TZ, ensure_utc


def utc_datetime_to_moscow_iso(dt: datetime) -> str:
    """Наивное время считается UTC; возвращает ISO 8601 со смещением Москвы."""

    return ensure_utc(dt).astimezone(MOSCOW_TZ).isoformat()


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
