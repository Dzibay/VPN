"""Учёт устройств подписки: отпечаток заголовков, лимит, регистрация и список."""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import Settings
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User


def _norm_header(headers: Request.headers, key: str) -> str | None:
    raw = headers.get(key)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def subscription_device_fingerprint(request: Request) -> str:
    """
    Happ / v2raytun / FlClash передают x-hwid; без него — устойчивый ключ из типичных заголовков.
    """
    headers = request.headers
    hwid = _norm_header(headers, "x-hwid")
    if hwid:
        return f"hw:{hwid.strip().lower()}"
    ua = (_norm_header(headers, "user-agent") or "").encode("utf-8", errors="replace")
    dm = (_norm_header(headers, "x-device-model") or "").encode("utf-8", errors="replace")
    dos = (_norm_header(headers, "x-device-os") or "").encode("utf-8", errors="replace")
    vos = (_norm_header(headers, "x-ver-os") or "").encode("utf-8", errors="replace")
    h = hashlib.sha256(b"|".join((ua, dm, dos, vos))).hexdigest()
    return f"hdr:{h}"


def effective_subscription_device_limit(settings: Settings) -> int | None:
    """
    Положительное число — лимит разных устройств; None — без ограничения.

    Значение берётся из ``settings.subscription_max_devices`` (переменная окружения SUBSCRIPTION_MAX_DEVICES).
    Любое значение ≤ 0 означает «без лимита».
    """
    lim = int(settings.subscription_max_devices)
    if lim <= 0:
        return None
    return lim


def _device_row_fields(request: Request) -> dict:
    headers = request.headers
    now = utc_now()
    return {
        "user_agent": _norm_header(headers, "user-agent"),
        "os": _norm_header(headers, "x-device-os"),
        "hwid_raw": _norm_header(headers, "x-hwid"),
        "updated_at": now,
    }


async def register_or_touch_subscription_device(
    session: AsyncSession,
    *,
    settings: Settings,
    user: User,
    request: Request,
) -> bool:
    """
    Сохраняет или обновляет запись устройства.

    Лимит уникальных устройств проверяется здесь всегда (включая истёкшую подписку), если в API
    задано положительное ``SUBSCRIPTION_MAX_DEVICES``. Новое устройство при исчерпанном лимите
    не регистрируется — возвращается ``False``; обработчик /sub отдаёт пустой список узлов и
    текст в заголовке ``announce``.

    Запись не создаётся и не обновляется, если нет заголовков ``User-Agent`` или ``x-device-os``
    (подписку при этом всё равно можно отдать — возвращается ``True``).

    :returns: ``True``, если клиенту можно выдавать узлы (известное устройство или успешная регистрация).
    """
    # Без User-Agent не фиксируем устройство (превью ссылки, скрейперы и т.п.).
    if _norm_header(request.headers, "user-agent") is None:
        return True
    # Без x-device-os не фиксируем (открытие /sub в браузере и клиенты без метки ОС приложения).
    if _norm_header(request.headers, "x-device-os") is None:
        return True

    fingerprint = subscription_device_fingerprint(request)
    limit = effective_subscription_device_limit(settings)

    # Сериализуем по пользователю, чтобы два новых клиента параллельно не превысили лимит.
    await session.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": int(user.id)})

    row = (
        await session.execute(
            select(SubscriptionDevice).where(
                SubscriptionDevice.user_id == user.id,
                SubscriptionDevice.fingerprint == fingerprint,
            )
        )
    ).scalar_one_or_none()

    fields = _device_row_fields(request)

    if row is None:
        if limit is not None:
            cnt = (
                await session.execute(
                    select(func.count()).select_from(SubscriptionDevice).where(
                        SubscriptionDevice.user_id == user.id,
                    )
                )
            ).scalar_one()
            if int(cnt or 0) >= limit:
                return False
        now = utc_now()
        session.add(
            SubscriptionDevice(
                user_id=user.id,
                fingerprint=fingerprint,
                created_at=now,
                **fields,
            )
        )
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    return True


async def list_subscription_connection_records(
    session: AsyncSession, user_id: int
) -> list[dict[str, int | str | None]]:
    rows = (
        await session.execute(
            select(
                SubscriptionDevice.id,
                SubscriptionDevice.os,
                SubscriptionDevice.user_agent,
            )
            .where(SubscriptionDevice.user_id == user_id)
            .order_by(SubscriptionDevice.updated_at.desc()),
        )
    ).all()
    return [{"id": int(r[0]), "os": r[1], "user_agent": r[2]} for r in rows]


async def list_subscription_connection_records_for_users(
    session: AsyncSession,
    user_ids: list[int],
) -> dict[int, list[dict[str, int | str | None]]]:
    """Те же поля, что у ``list_subscription_connection_records``, одним запросом по многим user_id."""
    if not user_ids:
        return {}
    rows = (
        await session.execute(
            select(
                SubscriptionDevice.user_id,
                SubscriptionDevice.id,
                SubscriptionDevice.os,
                SubscriptionDevice.user_agent,
            )
            .where(SubscriptionDevice.user_id.in_(user_ids))
            .order_by(SubscriptionDevice.user_id, SubscriptionDevice.updated_at.desc()),
        )
    ).all()
    out: dict[int, list[dict[str, int | str | None]]] = {}
    for uid, did, os_val, ua in rows:
        uid_i = int(uid)
        bucket = out.setdefault(uid_i, [])
        bucket.append({"id": int(did), "os": os_val, "user_agent": ua})
    return out


async def count_subscription_devices_for_user(session: AsyncSession, user_id: int) -> int:
    n = (
        await session.execute(
            select(func.count())
            .select_from(SubscriptionDevice)
            .where(SubscriptionDevice.user_id == user_id),
        )
    ).scalar_one()
    return int(n or 0)
