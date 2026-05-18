"""Tribute: webhook подписки и разовой цифровой покупки; публичные тарифы — ``app/data/tribute_tariffs.json``.

Подписка: ``new_subscription`` / ``renewed_subscription`` — ``period``, ``price``, ``expires_at``, ``telegram_user_id``.

Разовая покупка: ``new_digital_product`` — срок из ``months`` / ``period`` в payload, иначе точное совпадение
``product_name`` с ``app.constants.TRIBUTE_DIGITAL_PRODUCT_NAME_*``. HMAC: заголовок ``trbt-signature``, ключ
``TRIBUTE_API_KEY``.

``cancelled_subscription`` и ``digital_product_refunded`` — без изменений в БД (заглушки).

Успешные оплаты пишутся в ``payments.tribute_webhook`` (JSONB ``{name, payload}`` — полное тело webhook).
Без ``telegram_user_id`` — запись в ``payments`` с ``user_id = null`` (без продления подписки и задач).
Дедупликация: ``purchase_id`` для ``new_digital_product``; ``subscription_id`` + ``expires_at`` для подписки.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import constants
from app.config import Settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError, UnauthorizedError
from app.core.time import utc_today
from app.domain.models.payments import (
    TributePaymentsLinksResponse,
    TributeWebhookAck,
)
from app.domain.referrals.payment_tasks import apply_referral_bonus_on_payment
from app.domain.referrals.task_bonus_days import sum_referral_bonus_days_pending_activation
from app.domain.services.telegram_service import require_user_by_telegram_id
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.tribute_service")

_DAYS_PER_MONTH = 31

_TRIBUTE_TARIFFS_JSON = Path(__file__).resolve().parents[2] / "data" / "tribute_tariffs.json"


def tribute_payments_links_public_response() -> TributePaymentsLinksResponse:
    """Ответ совпадает с содержимым ``app/data/tribute_tariffs.json`` (редактируйте файл)."""
    try:
        raw = _TRIBUTE_TARIFFS_JSON.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("Не удалось прочитать %s: %s", _TRIBUTE_TARIFFS_JSON, e)
        return TributePaymentsLinksResponse(tariffs=[])
    try:
        return TributePaymentsLinksResponse.model_validate_json(raw)
    except ValidationError:
        log.exception("Некорректный JSON тарифов: %s", _TRIBUTE_TARIFFS_JSON)
        return TributePaymentsLinksResponse(tariffs=[])


_PERIOD_TO_MONTHS: dict[str, int] = {
    "monthly": 1,
    "quarterly": 3,
    "biannual": 6,
    "semiannual": 6,
    "half_yearly": 6,
    "yearly": 12,
}

_MONTHS_TO_PERIOD: dict[int, str] = {
    1: "monthly",
    3: "quarterly",
    6: "biannual",
    12: "yearly",
}


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


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    """ISO-8601 UTC для JSONB tribute_webhook (как в теле webhook Tribute)."""
    return _ensure_utc(dt).isoformat().replace("+00:00", "Z")


def _period_to_months(period: str) -> int | None:
    return _PERIOD_TO_MONTHS.get((period or "").strip().lower())


def _extend_subscription_until(base: date | None, *, days: int) -> date:
    if days < 1:
        raise ValueError("days must be >= 1")
    today = utc_today()
    start = base if base is not None and base >= today else today
    return start + timedelta(days=days)


class _TributeWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    payload: dict[str, Any]


class _SubscriptionPaidPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    subscription_id: int
    period: str
    price: int
    expires_at: datetime
    telegram_user_id: int | None = None
    type: Literal["regular", "gift", "trial"] | None = None


class _SubscriptionCancelledPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    subscription_id: int
    expires_at: datetime
    telegram_user_id: int | None = None
    cancel_reason: str | None = None


class _DigitalProductPaidPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: int
    amount: int
    purchase_id: int
    telegram_user_id: int | None = None
    transaction_id: int | None = None
    product_name: str | None = None
    purchase_created_at: datetime | None = None
    currency: str | None = None
    months: int | None = Field(default=None, ge=1, le=120)
    period: str | None = None


def _resolve_new_digital_product_months(p: _DigitalProductPaidPayload) -> int | None:
    if p.months is not None:
        m = int(p.months)
        if 1 <= m <= 120:
            return m
    if p.period:
        mapped = _period_to_months(p.period)
        if mapped is not None:
            return mapped
    pn = (p.product_name or "").strip()
    if not pn:
        return None
    for label, months in (
        (constants.TRIBUTE_DIGITAL_PRODUCT_NAME_1M, 1),
        (constants.TRIBUTE_DIGITAL_PRODUCT_NAME_3M, 3),
        (constants.TRIBUTE_DIGITAL_PRODUCT_NAME_6M, 6),
        (constants.TRIBUTE_DIGITAL_PRODUCT_NAME_1Y, 12),
    ):
        cfg = (label or "").strip()
        if cfg and cfg == pn:
            return months
    return None


def _tribute_webhook_envelope(*, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"name": event_name, "payload": payload}


async def _tribute_payment_duplicate(
    session: AsyncSession,
    *,
    webhook: dict[str, Any],
) -> bool:
    name = (webhook.get("name") or "").strip()
    payload = webhook.get("payload")
    if not isinstance(payload, dict):
        return False

    if name == "new_digital_product":
        purchase_id = payload.get("purchase_id")
        if purchase_id is None:
            return False
        stmt = (
            select(Payment.id)
            .where(
                Payment.provider == "tribute",
                Payment.tribute_webhook["name"].astext == name,
                Payment.tribute_webhook["payload"]["purchase_id"].as_integer() == int(purchase_id),
            )
            .limit(1)
        )
    elif name in ("new_subscription", "renewed_subscription"):
        subscription_id = payload.get("subscription_id")
        expires_at = payload.get("expires_at")
        if subscription_id is None or expires_at is None:
            return False
        stmt = (
            select(Payment.id)
            .where(
                Payment.provider == "tribute",
                Payment.tribute_webhook["payload"]["subscription_id"].as_integer()
                == int(subscription_id),
                Payment.tribute_webhook["payload"]["expires_at"].astext == str(expires_at),
            )
            .limit(1)
        )
    else:
        return False

    return (await session.scalars(stmt)).first() is not None


async def _commit_tribute_paid_months(
    session: AsyncSession,
    settings: Settings,
    *,
    telegram_user_id: int | None,
    months: int,
    amount_minor: int,
    tribute_webhook: dict[str, Any],
    payment_kind: Literal["subscription", "one_time"],
    event_name: str,
    created_at: datetime | None = None,
) -> TributeWebhookAck:
    if await _tribute_payment_duplicate(session, webhook=tribute_webhook):
        return TributeWebhookAck(ok=True, event=event_name, duplicate=True)

    amount_decimal = _amount_from_minor_units(int(amount_minor))
    paid_at = _ensure_utc(created_at) if created_at is not None else None

    if telegram_user_id is None:
        log.warning(
            "Tribute %s: нет telegram_user_id — платёж без пользователя (webhook сохранён)",
            event_name,
        )
        session.add(
            Payment(
                user_id=None,
                amount=amount_decimal,
                months=months,
                provider="tribute",
                payment_kind=payment_kind,
                tribute_webhook=tribute_webhook,
                **({"created_at": paid_at} if paid_at is not None else {}),
            ),
        )
        await session.flush()
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    user = await require_user_by_telegram_id(session, int(telegram_user_id))

    paid_days = int(months) * _DAYS_PER_MONTH

    accumulated_bonus_days = await sum_referral_bonus_days_pending_activation(
        session,
        user_id=int(user.id),
    )
    total_days = paid_days + accumulated_bonus_days
    user.subscription_until = _extend_subscription_until(user.subscription_until, days=total_days)

    session.add(
        Payment(
            user_id=int(user.id),
            amount=amount_decimal,
            months=months,
            provider="tribute",
            payment_kind=payment_kind,
            tribute_webhook=tribute_webhook,
            **({"created_at": paid_at} if paid_at is not None else {}),
        ),
    )
    session.add(
        Task(
            task_type="notify_payment",
            user_id=int(user.id),
            referee_id=None,
            bonus_days=accumulated_bonus_days if accumulated_bonus_days > 0 else None,
            paid_months=months,
            **({"created_at": paid_at} if paid_at is not None else {}),
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
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    webhook = _tribute_webhook_envelope(event_name=event_name, payload=payload)

    return await _commit_tribute_paid_months(
        session,
        settings,
        telegram_user_id=int(p.telegram_user_id) if p.telegram_user_id is not None else None,
        months=months,
        amount_minor=int(p.price),
        tribute_webhook=webhook,
        payment_kind="subscription",
        event_name=event_name,
    )


async def _handle_digital_product_paid(
    session: AsyncSession,
    *,
    settings: Settings,
    payload: dict[str, Any],
) -> TributeWebhookAck:
    p = _DigitalProductPaidPayload.model_validate(payload)
    event_name = "new_digital_product"

    months = _resolve_new_digital_product_months(p)
    if months is None:
        log.warning(
            "Tribute new_digital_product: неизвестный срок (product_id=%s purchase_id=%s product_name=%r)",
            p.product_id,
            p.purchase_id,
            (p.product_name or "")[:200],
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    webhook = _tribute_webhook_envelope(event_name=event_name, payload=payload)

    return await _commit_tribute_paid_months(
        session,
        settings,
        telegram_user_id=int(p.telegram_user_id) if p.telegram_user_id is not None else None,
        months=months,
        amount_minor=int(p.amount),
        tribute_webhook=webhook,
        payment_kind="one_time",
        event_name=event_name,
    )


async def _handle_subscription_cancelled(*, payload: dict[str, Any]) -> TributeWebhookAck:
    _SubscriptionCancelledPayload.model_validate(payload)
    return TributeWebhookAck(ok=True, event="cancelled_subscription", duplicate=False)


async def _handle_digital_product_refunded(*, payload: dict[str, Any]) -> TributeWebhookAck:
    return TributeWebhookAck(ok=True, event="digital_product_refunded", duplicate=False)


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

    if isinstance(body_obj, dict) and "test_event" in body_obj and "name" not in body_obj:
        te = body_obj.get("test_event")
        return TributeWebhookAck(ok=True, event=str(te) if te is not None else "test_event", duplicate=False)

    env = _TributeWebhookEnvelope.model_validate(body_obj)
    return await process_tribute_webhook_event(
        session,
        settings=settings,
        name=env.name,
        payload=env.payload,
    )


def _admin_manual_external_id(*, telegram_user_id: int, paid_at: datetime) -> int:
    """Отрицательный id для admin_manual: влезает в PostgreSQL INTEGER, не как у Tribute."""
    paid_at_utc = _ensure_utc(paid_at)
    # Нельзя timestamp()*1000 — ~1.7e12, CAST AS INTEGER падает с NumericValueOutOfRange.
    return -(int(paid_at_utc.timestamp()) + int(telegram_user_id) % 100_000)


def _admin_manual_tribute_webhook(
    *,
    payment_kind: Literal["subscription", "one_time"],
    months: int,
    amount_minor: int,
    telegram_user_id: int,
    paid_at: datetime,
) -> tuple[str, dict[str, Any]]:
    """Синтетический webhook для админки; уникальные id — чтобы не попасть в дедуп."""
    paid_at_utc = _ensure_utc(paid_at)
    unique = _admin_manual_external_id(telegram_user_id=telegram_user_id, paid_at=paid_at_utc)
    if payment_kind == "one_time":
        return (
            "new_digital_product",
            {
                "product_id": 0,
                "amount": int(amount_minor),
                "purchase_id": unique,
                "telegram_user_id": int(telegram_user_id),
                "months": int(months),
                "product_name": "admin_manual",
                "purchase_created_at": _iso_utc(paid_at_utc),
            },
        )
    period = _MONTHS_TO_PERIOD.get(int(months), "monthly")
    expires_at = paid_at_utc + timedelta(days=int(months) * _DAYS_PER_MONTH)
    return (
        "new_subscription",
        {
            "subscription_id": unique,
            "period": period,
            "price": int(amount_minor),
            "expires_at": _iso_utc(expires_at),
            "telegram_user_id": int(telegram_user_id),
            "type": "regular",
        },
    )


async def staff_apply_tribute_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    months: int,
    amount_minor: int,
    payment_kind: Literal["subscription", "one_time"],
    created_at: datetime | None = None,
) -> TributeWebhookAck:
    """Ручное начисление: тот же ``_commit_tribute_paid_months``, что после webhook Tribute."""
    user = await session.get(User, int(user_id))
    if user is None:
        raise LookupError("user_not_found")
    if user.telegram_id is None:
        raise LookupError("telegram_id_missing")

    paid_at = _ensure_utc(created_at) if created_at is not None else datetime.now(timezone.utc)

    event_name, payload = _admin_manual_tribute_webhook(
        payment_kind=payment_kind,
        months=int(months),
        amount_minor=int(amount_minor),
        telegram_user_id=int(user.telegram_id),
        paid_at=paid_at,
    )
    webhook = _tribute_webhook_envelope(event_name=event_name, payload=payload)
    return await _commit_tribute_paid_months(
        session,
        settings,
        telegram_user_id=int(user.telegram_id),
        months=int(months),
        amount_minor=int(amount_minor),
        tribute_webhook=webhook,
        payment_kind=payment_kind,
        event_name=event_name,
        created_at=paid_at,
    )


async def process_tribute_webhook_event(
    session: AsyncSession,
    *,
    settings: Settings,
    name: str,
    payload: dict[str, Any],
) -> TributeWebhookAck:
    """Диспетчер по ``name`` (реальный webhook и ``/webhook-test``)."""
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
    if n == "new_digital_product":
        return await _handle_digital_product_paid(session, settings=settings, payload=payload)
    if n == "digital_product_refunded":
        return await _handle_digital_product_refunded(payload=payload)
    log.warning("Tribute webhook: неизвестное событие name=%r", n)
    return TributeWebhookAck(ok=True, event=n or None, duplicate=False)
