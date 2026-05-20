"""Tribute: webhook подписки и разовой цифровой покупки; публичные тарифы — ``app/data/tribute_tariffs.json``.

Каждый HTTP webhook пишется в ``user_http_request_traces`` (см. ``http_audit_always_persist_for_path``).
В ``payments`` всегда создаётся строка с полным ``tribute_webhook`` (если не дубликат). Продление подписки,
задачи и реферальные бонусы — только при полном наборе данных.

HMAC: заголовок ``trbt-signature``, ключ ``TRIBUTE_API_KEY``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import constants
from app.config import Settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError, UnauthorizedError
from app.core.time import utc_today
from app.domain.models.payments import (
    TributePaymentsLinksResponse,
    TributeWebhookAck,
)
from app.core.request_subject import bind_request_subject_user
from app.domain.referrals.payment_tasks import apply_referral_bonus_on_payment
from app.domain.referrals.task_bonus_days import sum_referral_bonus_days_pending_activation
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.tribute_service")

_DAYS_PER_MONTH = 31

_TRIBUTE_TARIFFS_JSON = Path(__file__).resolve().parents[2] / "data" / "tribute_tariffs.json"

_PAID_SUBSCRIPTION_EVENTS = frozenset({"new_subscription", "renewed_subscription"})
_PAID_DIGITAL_EVENTS = frozenset({"new_digital_product"})


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


@dataclass(frozen=True)
class _TributeWebhookParsed:
    payment_kind: Literal["subscription", "one_time"]
    amount_minor: int
    months: int
    telegram_user_id: int | None
    fulfill: bool
    skip_reason: str | None
    created_at: datetime | None = None


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

    subscription_id: int | None = None
    period: str | None = None
    price: int | None = None
    expires_at: datetime | None = None
    telegram_user_id: int | None = None
    type: Literal["regular", "gift", "trial"] | None = None


class _DigitalProductPaidPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: int | None = None
    amount: int | None = None
    purchase_id: int | None = None
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


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_subscription_paid(*, event_name: str, payload: dict[str, Any]) -> _TributeWebhookParsed:
    try:
        p = _SubscriptionPaidPayload.model_validate(payload)
    except ValidationError:
        p = _SubscriptionPaidPayload()

    months = _period_to_months(p.period or str(payload.get("period") or "")) or 0
    amount_minor = _coerce_int(p.price if p.price is not None else payload.get("price")) or 0
    telegram_user_id = _coerce_int(
        p.telegram_user_id if p.telegram_user_id is not None else payload.get("telegram_user_id"),
    )
    sub_type = (p.type or payload.get("type") or "regular")
    if isinstance(sub_type, str):
        sub_type_norm = sub_type.strip().lower()
    else:
        sub_type_norm = "regular"

    skip_reason: str | None = None
    fulfill = event_name in _PAID_SUBSCRIPTION_EVENTS
    if sub_type_norm == "gift":
        fulfill = False
        skip_reason = "gift"
    elif months < 1:
        fulfill = False
        skip_reason = "unknown_period"
    elif telegram_user_id is None:
        fulfill = False
        skip_reason = "no_telegram_user_id"

    return _TributeWebhookParsed(
        payment_kind="subscription",
        amount_minor=amount_minor,
        months=months,
        telegram_user_id=telegram_user_id,
        fulfill=fulfill,
        skip_reason=skip_reason,
    )


def _parse_digital_product_paid(*, payload: dict[str, Any]) -> _TributeWebhookParsed:
    try:
        p = _DigitalProductPaidPayload.model_validate(payload)
    except ValidationError:
        p = _DigitalProductPaidPayload()

    months = _resolve_new_digital_product_months(p) or 0
    amount_minor = _coerce_int(p.amount if p.amount is not None else payload.get("amount")) or 0
    telegram_user_id = _coerce_int(
        p.telegram_user_id if p.telegram_user_id is not None else payload.get("telegram_user_id"),
    )
    created_at = p.purchase_created_at
    if created_at is None and payload.get("purchase_created_at"):
        try:
            created_at = _DigitalProductPaidPayload.model_validate(
                {"purchase_created_at": payload.get("purchase_created_at")},
            ).purchase_created_at
        except ValidationError:
            created_at = None

    skip_reason: str | None = None
    fulfill = True
    if months < 1:
        fulfill = False
        skip_reason = "unknown_term"
    elif telegram_user_id is None:
        fulfill = False
        skip_reason = "no_telegram_user_id"

    return _TributeWebhookParsed(
        payment_kind="one_time",
        amount_minor=amount_minor,
        months=months,
        telegram_user_id=telegram_user_id,
        fulfill=fulfill,
        skip_reason=skip_reason,
        created_at=created_at,
    )


def _parse_generic_webhook(
    *,
    event_name: str,
    payment_kind: Literal["subscription", "one_time"],
    skip_reason: str,
) -> _TributeWebhookParsed:
    return _TributeWebhookParsed(
        payment_kind=payment_kind,
        amount_minor=0,
        months=0,
        telegram_user_id=None,
        fulfill=False,
        skip_reason=skip_reason,
    )


async def _find_duplicate_payment_id(
    session: AsyncSession,
    *,
    webhook: dict[str, Any],
) -> int | None:
    name = (webhook.get("name") or "").strip()
    payload = webhook.get("payload")
    if not isinstance(payload, dict):
        return None

    if name == "new_digital_product":
        purchase_id = payload.get("purchase_id")
        if purchase_id is None:
            return None
        stmt = (
            select(Payment.id)
            .where(
                Payment.provider == "tribute",
                Payment.tribute_webhook["name"].astext == name,
                Payment.tribute_webhook["payload"]["purchase_id"].as_integer() == int(purchase_id),
            )
            .limit(1)
        )
    elif name in _PAID_SUBSCRIPTION_EVENTS:
        subscription_id = payload.get("subscription_id")
        expires_at = payload.get("expires_at")
        if subscription_id is None or expires_at is None:
            return None
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
        return None

    row = (await session.scalars(stmt)).first()
    return int(row) if row is not None else None


async def _find_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == int(telegram_id)).limit(1)
    return (await session.scalars(stmt)).first()


async def _fulfill_tribute_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    months: int,
    paid_at: datetime | None,
) -> None:
    paid_days = int(months) * _DAYS_PER_MONTH
    accumulated_bonus_days = await sum_referral_bonus_days_pending_activation(
        session,
        user_id=int(user.id),
    )
    total_days = paid_days + accumulated_bonus_days
    user.subscription_until = _extend_subscription_until(user.subscription_until, days=total_days)

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


async def _ingest_tribute_webhook(
    session: AsyncSession,
    settings: Settings,
    *,
    event_name: str,
    payload: dict[str, Any],
    parsed: _TributeWebhookParsed,
) -> TributeWebhookAck:
    webhook = _tribute_webhook_envelope(event_name=event_name, payload=payload)

    dup_id = await _find_duplicate_payment_id(session, webhook=webhook)
    if dup_id is not None:
        skip_reason = parsed.skip_reason or "duplicate"
        log.warning("Tribute %s: дубликат webhook (payment_id=%s)", event_name, dup_id)
        return TributeWebhookAck(
            ok=True,
            event=event_name,
            duplicate=True,
            payment_id=dup_id,
            fulfilled=False,
            skip_reason=skip_reason,
        )

    amount_decimal = _amount_from_minor_units(parsed.amount_minor)
    paid_at = _ensure_utc(parsed.created_at) if parsed.created_at is not None else None
    payment_user_id: int | None = None
    fulfilled = False
    skip_reason = parsed.skip_reason

    payment = Payment(
        user_id=None,
        amount=amount_decimal,
        months=max(0, int(parsed.months)),
        provider="tribute",
        payment_kind=parsed.payment_kind,
        tribute_webhook=webhook,
        **({"created_at": paid_at} if paid_at is not None else {}),
    )

    try:
        async with session.begin_nested():
            session.add(payment)
            await session.flush()
    except IntegrityError:
        existing_id = await _find_duplicate_payment_id(session, webhook=webhook)
        if existing_id is None:
            raise
        skip_reason = parsed.skip_reason or "duplicate"
        return TributeWebhookAck(
            ok=True,
            event=event_name,
            duplicate=True,
            payment_id=existing_id,
            fulfilled=False,
            skip_reason=skip_reason,
        )

    payment_id = int(payment.id)

    if parsed.fulfill and parsed.telegram_user_id is not None and parsed.months >= 1:
        user = await _find_user_by_telegram_id(session, int(parsed.telegram_user_id))
        if user is None:
            skip_reason = "user_not_found"
            log.warning(
                "Tribute %s: пользователь telegram_id=%s не найден — платёж %s без продления",
                event_name,
                parsed.telegram_user_id,
                payment_id,
            )
        else:
            payment_user_id = int(user.id)
            payment.user_id = payment_user_id
            bind_request_subject_user(payment_user_id, source="tribute_webhook")
            await _fulfill_tribute_payment(
                session,
                settings,
                user=user,
                months=int(parsed.months),
                paid_at=paid_at,
            )
            fulfilled = True
            skip_reason = None
            log.info(
                "Tribute %s: платёж %s, user_id=%s, months=%s",
                event_name,
                payment_id,
                payment_user_id,
                parsed.months,
            )
    elif parsed.fulfill and skip_reason is None:
        skip_reason = "incomplete_payload"

    await session.flush()

    return TributeWebhookAck(
        ok=True,
        event=event_name,
        duplicate=False,
        payment_id=payment_id,
        fulfilled=fulfilled,
        skip_reason=skip_reason,
    )


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
        event_name = str(te) if te is not None else "test_event"
        return await _ingest_tribute_webhook(
            session,
            settings,
            event_name=event_name,
            payload=body_obj,
            parsed=_parse_generic_webhook(
                event_name=event_name,
                payment_kind="subscription",
                skip_reason="test_event",
            ),
        )

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
    """Ручное начисление: тот же ingest, что после webhook Tribute."""
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
    if payment_kind == "one_time":
        parsed = _parse_digital_product_paid(payload=payload)
        parsed = _TributeWebhookParsed(
            payment_kind=parsed.payment_kind,
            amount_minor=parsed.amount_minor,
            months=int(months),
            telegram_user_id=int(user.telegram_id),
            fulfill=True,
            skip_reason=None,
            created_at=paid_at,
        )
    else:
        parsed = _TributeWebhookParsed(
            payment_kind="subscription",
            amount_minor=int(amount_minor),
            months=int(months),
            telegram_user_id=int(user.telegram_id),
            fulfill=True,
            skip_reason=None,
        )

    return await _ingest_tribute_webhook(
        session,
        settings,
        event_name=event_name,
        payload=payload,
        parsed=parsed,
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

    if n in _PAID_SUBSCRIPTION_EVENTS:
        parsed = _parse_subscription_paid(event_name=n, payload=payload)
        return await _ingest_tribute_webhook(
            session,
            settings,
            event_name=n,
            payload=payload,
            parsed=parsed,
        )

    if n == "cancelled_subscription":
        return await _ingest_tribute_webhook(
            session,
            settings,
            event_name=n,
            payload=payload,
            parsed=_parse_generic_webhook(
                event_name=n,
                payment_kind="subscription",
                skip_reason="cancelled_subscription",
            ),
        )

    if n == "new_digital_product":
        parsed = _parse_digital_product_paid(payload=payload)
        return await _ingest_tribute_webhook(
            session,
            settings,
            event_name=n,
            payload=payload,
            parsed=parsed,
        )

    if n == "digital_product_refunded":
        return await _ingest_tribute_webhook(
            session,
            settings,
            event_name=n,
            payload=payload,
            parsed=_parse_generic_webhook(
                event_name=n,
                payment_kind="one_time",
                skip_reason="digital_product_refunded",
            ),
        )

    log.warning("Tribute webhook: неизвестное событие name=%r", n)
    return await _ingest_tribute_webhook(
        session,
        settings,
        event_name=n or "unknown",
        payload=payload,
        parsed=_parse_generic_webhook(
            event_name=n or "unknown",
            payment_kind="subscription",
            skip_reason="unknown_event",
        ),
    )
