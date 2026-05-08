"""Tribute (рекуррентная подписка): выдача публичной ссылки и обработка webhook.

Webhook ловит события подписочной модели Tribute (см. OpenAPI ``tribute.tg/api/v1``):

- ``new_subscription`` — первая оплата подписки (создана/возобновлена пользователем);
- ``renewed_subscription`` — авто-продление за следующий период;
- ``cancelled_subscription`` — пользователь отменил автопродление; до ``expires_at`` доступ остаётся.

Все события защищены HMAC-SHA256 (заголовок ``trbt-signature``, ключ — ``TRIBUTE_API_KEY``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError, UnauthorizedError
from app.core.time import utc_today
from app.domain.models.payments import (
    TributeSubscriptionPublic,
    TributeSubscriptionResponse,
    TributeWebhookAck,
)
from app.domain.referrals.payment_tasks import apply_referral_bonus_on_payment
from app.domain.services.telegram_service import require_user_by_telegram_id
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task

log = logging.getLogger("app.tribute_service")

_DAYS_PER_MONTH = 31

_PERIOD_TO_MONTHS: dict[str, int] = {
    "monthly": 1,
    "quarterly": 3,
    "yearly": 12,
}


def tribute_subscription_public_response(settings: Settings) -> TributeSubscriptionResponse:
    sub = settings.tribute_subscription
    if sub is None:
        return TributeSubscriptionResponse(subscription=None)
    return TributeSubscriptionResponse(
        subscription=TributeSubscriptionPublic(
            tg_link=sub.tg_link,
            web_link=sub.web_link,
        ),
    )


def _require_tribute_api_key(settings: Settings) -> str:
    key = (settings.tribute_api_key or "").strip()
    if not key:
        raise ServiceUnavailableError(
            detail="TRIBUTE_API_KEY не задан: webhook Tribute отключён",
        )
    return key


def verify_tribute_webhook_signature(*, raw_body: bytes, header_signature: str | None, api_key: str) -> None:
    got = (header_signature or "").strip()
    if not got:
        raise UnauthorizedError(detail="Отсутствует заголовок trbt-signature")
    expected = hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(got, expected):
        raise UnauthorizedError(detail="Недействительная подпись webhook")


def _amount_from_minor_units(amount_minor: int) -> Decimal:
    return (Decimal(int(amount_minor)) * Decimal("0.01")).quantize(Decimal("0.01"))


def _period_to_months(period: str) -> int | None:
    return _PERIOD_TO_MONTHS.get((period or "").strip().lower())


def _expires_at_iso_compact(expires_at: datetime) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _extend_subscription_until(base: date | None, *, months: int) -> date:
    if months < 1:
        raise ValueError("months must be >= 1")
    today = utc_today()
    start = base if base is not None and base >= today else today
    return start + timedelta(days=months * _DAYS_PER_MONTH)


class _TributeWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    payload: dict[str, Any]


class _SubscriptionPaidPayload(BaseModel):
    """Объединённая схема для ``new_subscription`` и ``renewed_subscription``.

    Из всего, что присылает Tribute, нашему коду нужны только: ``subscription_id``,
    ``period``, ``price``, ``expires_at``, ``telegram_user_id`` и опционально ``type``
    (для пропуска ``gift``). Поля ``period_id``, ``amount``, ``currency`` отмечены
    как обязательные в схеме Tribute, но логикой не используются — поэтому здесь
    они опциональны (схема всё равно принимает их через ``extra="allow"``).
    """

    model_config = ConfigDict(extra="allow")

    subscription_id: int
    period: str
    price: int
    expires_at: datetime
    telegram_user_id: int | None = None
    type: Literal["regular", "gift", "trial"] | None = None


class _SubscriptionCancelledPayload(BaseModel):
    """Из ``cancelled_subscription`` нам нужны subscription_id, expires_at и (опц.) telegram_user_id."""

    model_config = ConfigDict(extra="allow")

    subscription_id: int
    expires_at: datetime
    telegram_user_id: int | None = None
    cancel_reason: str | None = None


async def _handle_subscription_paid(
    session: AsyncSession,
    *,
    settings: Settings,
    event_name: str,
    payload: dict[str, Any],
) -> TributeWebhookAck:
    p = _SubscriptionPaidPayload.model_validate(payload)

    months = _period_to_months(p.period)
    if months is None:
        log.warning(
            "Tribute %s: неизвестный period=%r (subscription_id=%s) — игнор",
            event_name,
            p.period,
            p.subscription_id,
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    if (p.type or "regular") == "gift":
        log.info(
            "Tribute %s: type=gift (subscription_id=%s) — пропускаем (платежа нет)",
            event_name,
            p.subscription_id,
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    if p.telegram_user_id is None:
        log.warning(
            "Tribute %s: payload.telegram_user_id отсутствует (subscription_id=%s) — игнор",
            event_name,
            p.subscription_id,
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    ext = (
        f"sub:{int(p.subscription_id)}"
        f":tg{int(p.telegram_user_id)}"
        f":{_expires_at_iso_compact(p.expires_at)}"
    )

    dup_stmt = (
        select(Payment.id)
        .where(Payment.provider == "tribute", Payment.external_id == ext)
        .limit(1)
    )
    if (await session.scalars(dup_stmt)).first() is not None:
        return TributeWebhookAck(ok=True, event=event_name, duplicate=True)

    user = await require_user_by_telegram_id(session, int(p.telegram_user_id))

    dup_stmt2 = (
        select(Payment.id)
        .where(Payment.provider == "tribute", Payment.external_id == ext)
        .limit(1)
    )
    if (await session.scalars(dup_stmt2)).first() is not None:
        return TributeWebhookAck(ok=True, event=event_name, duplicate=True)

    amount_decimal = _amount_from_minor_units(int(p.price))
    user.subscription_until = _extend_subscription_until(user.subscription_until, months=months)

    session.add(
        Payment(
            user_id=int(user.id),
            amount=amount_decimal,
            months=months,
            provider="tribute",
            external_id=ext,
        ),
    )
    session.add(
        Task(
            task_type="notify_payment",
            user_id=int(user.id),
            referee_id=None,
            bonus_days=None,
            paid_months=months,
        ),
    )
    await apply_referral_bonus_on_payment(
        session,
        settings=settings,
        referee_user_id=int(user.id),
        paid_months=months,
    )
    await session.flush()
    return TributeWebhookAck(ok=True, event=event_name, duplicate=False)


async def _handle_subscription_cancelled(
    *,
    payload: dict[str, Any],
) -> TributeWebhookAck:
    p = _SubscriptionCancelledPayload.model_validate(payload)
    log.info(
        "Tribute cancelled_subscription: telegram_user_id=%s subscription_id=%s expires_at=%s reason=%r — "
        "доступ сохраняется до expires_at, отдельных действий не требуется",
        p.telegram_user_id,
        p.subscription_id,
        p.expires_at.isoformat(),
        p.cancel_reason or "",
    )
    return TributeWebhookAck(ok=True, event="cancelled_subscription", duplicate=False)


async def process_tribute_webhook_raw_body(
    session: AsyncSession,
    *,
    settings: Settings,
    raw_body: bytes,
    trbt_signature: str | None,
) -> TributeWebhookAck:
    api_key = _require_tribute_api_key(settings)
    verify_tribute_webhook_signature(raw_body=raw_body, header_signature=trbt_signature, api_key=api_key)

    try:
        body_obj: Any = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BadRequestError(detail="Некорректный JSON тела webhook") from None

    # Дашборд Tribute при «тестовом запросе» шлёт {"test_event": "..."} без name/payload.
    if isinstance(body_obj, dict) and "test_event" in body_obj and "name" not in body_obj:
        log.info("Tribute webhook: тестовое событие test_event=%r", body_obj.get("test_event"))
        te = body_obj.get("test_event")
        return TributeWebhookAck(ok=True, event=str(te) if te is not None else "test_event", duplicate=False)

    env = _TributeWebhookEnvelope.model_validate(body_obj)
    return await process_tribute_webhook_event(
        session,
        settings=settings,
        name=env.name,
        payload=env.payload,
    )


async def process_tribute_webhook_event(
    session: AsyncSession,
    *,
    settings: Settings,
    name: str,
    payload: dict[str, Any],
) -> TributeWebhookAck:
    """Диспетчер по ``name``. Используется и реальным webhook'ом, и тестовым эндпоинтом."""
    n = (name or "").strip()
    if n in ("new_subscription", "renewed_subscription"):
        return await _handle_subscription_paid(
            session,
            settings=settings,
            event_name=n,
            payload=payload,
        )
    if n == "cancelled_subscription":
        return await _handle_subscription_cancelled(payload=payload)
    log.info("Tribute webhook: неизвестное событие name=%r — игнор", n)
    return TributeWebhookAck(ok=True, event=n or None, duplicate=False)
