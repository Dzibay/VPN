"""Учёт устройств по запросам /sub/{token} и лимит одновременных привязок."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.config import Settings
from app.models.subscription_device import SubscriptionDevice
from app.models.user import User


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
    now = datetime.now(timezone.utc)
    return {
        "user_agent": _norm_header(headers, "user-agent"),
        "os": _norm_header(headers, "x-device-os"),
        "hwid_raw": _norm_header(headers, "x-hwid"),
        "updated_at": now,
    }


def register_or_touch_subscription_device(
    session: Session,
    *,
    settings: Settings,
    user: User,
    request: Request,
) -> None:
    """
    Сохраняет или обновляет запись устройства.

    Лимит уникальных устройств проверяется здесь всегда (включая истёкшую подписку), если в API
    задано положительное ``SUBSCRIPTION_MAX_DEVICES``. Ответ без узлов VPN при неактивной
    подписке формируется уже после этого в обработчике /sub.
    """
    fingerprint = subscription_device_fingerprint(request)
    limit = effective_subscription_device_limit(settings)

    # Сериализуем по пользователю, чтобы два новых клиента параллельно не превысили лимит.
    session.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": int(user.id)})

    row = session.execute(
        select(SubscriptionDevice).where(
            SubscriptionDevice.user_id == user.id,
            SubscriptionDevice.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()

    fields = _device_row_fields(request)

    if row is None:
        if limit is not None:
            cnt = session.execute(
                select(func.count()).select_from(SubscriptionDevice).where(
                    SubscriptionDevice.user_id == user.id,
                )
            ).scalar_one()
            if int(cnt or 0) >= limit:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Достигнут лимит количества устройств для этой подписки "
                        "(каждый клиент с уникальным HWID считается отдельным устройством)."
                    ),
                )
        now = datetime.now(timezone.utc)
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


def list_subscription_connection_records(
    session: Session, user_id: int
) -> list[dict[str, int | str | None]]:
    rows = session.execute(
        select(
            SubscriptionDevice.id,
            SubscriptionDevice.os,
            SubscriptionDevice.user_agent,
        )
        .where(SubscriptionDevice.user_id == user_id)
        .order_by(SubscriptionDevice.updated_at.desc()),
    ).all()
    return [{"id": int(r[0]), "os": r[1], "user_agent": r[2]} for r in rows]


def count_subscription_devices_for_user(session: Session, user_id: int) -> int:
    n = session.execute(
        select(func.count())
        .select_from(SubscriptionDevice)
        .where(SubscriptionDevice.user_id == user_id),
    ).scalar_one()
    return int(n or 0)