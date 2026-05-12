"""Tribute: webhook подписки и разовой цифровой покупки, плюс публичные ссылки (тарифы + рекуррент).

Подписка (``new_subscription`` / ``renewed_subscription``): payload с ``subscription_id``,
``period``, ``price``, ``expires_at``, ``telegram_user_id`` — см. OpenAPI ``tribute.tg/api/v1``.

Разовая покупка (``new_digital_product``): ``purchase_id``, ``product_id``, ``amount``, ``telegram_user_id``;
срок продления — из ``months`` (целое 1…120) и/или ``period`` (как у подписки: monthly, quarterly, …),
либо из дополнительных полей payload (см. ``_months_from_digital_product_payload``). См. OpenAPI
``NewDigitalProductPayload``; неизвестные поля принимаются через ``extra="allow"``.

``cancelled_subscription`` — только лог. ``digital_product_refunded`` — только лог (откат
подписки в этом сервисе не реализован).

Все события с телом JSON защищены HMAC-SHA256 (заголовок ``trbt-signature``, ключ ``TRIBUTE_API_KEY``).

Входящее тело каждого webhook пишется в лог (уровень INFO, логгер ``app.tribute_service``):
полный JSON как пришёл от Tribute (реальный ``POST /tribute/webhook``) или объект ``{name, payload}``
для ``POST …/webhook-test``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

log = logging.getLogger("app.tribute_service")

_DAYS_PER_MONTH = 31

_PERIOD_TO_MONTHS: dict[str, int] = {
    "monthly": 1,
    "quarterly": 3,
    "biannual": 6,
    "semiannual": 6,
    "half_yearly": 6,
    "yearly": 12,
}


def tribute_payments_links_public_response(settings: Settings) -> TributePaymentsLinksResponse:
    tariffs = settings.tribute_tariffs_web
    recurring = settings.tribute_recurring_pay
    if tariffs is None and recurring is None:
        return TributePaymentsLinksResponse(tariffs=None, recurring_pay=None)
    return TributePaymentsLinksResponse(tariffs=tariffs, recurring_pay=recurring)


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


def _log_tribute_webhook_incoming(body: Any) -> None:
    """Печатает в лог полную структуру тела webhook (как пришло от Tribute / тест-клиента)."""
    try:
        text = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = repr(body)
    log.info("Tribute webhook — полное тело:\n%s", text)


def _period_to_months(period: str) -> int | None:
    return _PERIOD_TO_MONTHS.get((period or "").strip().lower())


def _expires_at_iso_compact(expires_at: datetime) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
    """Объединённая схема для ``new_subscription`` и ``renewed_subscription``."""

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
    """Схема ``new_digital_product`` (см. OpenAPI ``NewDigitalProductPayload`` + опциональный срок)."""

    model_config = ConfigDict(extra="allow")

    product_id: int
    amount: int
    purchase_id: int
    telegram_user_id: int | None = None
    transaction_id: int | None = None
    product_name: str | None = None
    purchase_created_at: datetime | None = None
    currency: str | None = None
    months: int | None = Field(
        default=None,
        ge=1,
        le=120,
        description="Срок оплаты в месяцах, если Tribute передаёт в webhook.",
    )
    period: str | None = Field(
        default=None,
        description="Период как у подписки (monthly, quarterly, …), если передаётся.",
    )


def _months_from_digital_product_payload(p: _DigitalProductPaidPayload) -> int | None:
    """Срок в месяцах из тела ``new_digital_product`` (явные поля и распространённые доп. ключи)."""
    if p.months is not None:
        m = int(p.months)
        if 1 <= m <= 120:
            return m
    if p.period:
        mapped = _period_to_months(p.period)
        if mapped is not None:
            return mapped
    extra = p.model_extra or {}
    for key in ("paid_months", "subscription_months", "duration_months", "months_paid", "period_months"):
        v = extra.get(key)
        if isinstance(v, int) and 1 <= v <= 120:
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            n = int(v.strip())
            if 1 <= n <= 120:
                return n
    pe = extra.get("period")
    if isinstance(pe, str):
        mapped = _period_to_months(pe)
        if mapped is not None:
            return mapped
    return None


async def _commit_tribute_paid_months(
    session: AsyncSession,
    settings: Settings,
    *,
    telegram_user_id: int,
    months: int,
    amount_minor: int,
    external_id: str,
    payment_kind: Literal["subscription", "one_time"],
    event_name: str,
) -> TributeWebhookAck:
    """Идемпотентная запись платежа Tribute и продление ``users.subscription_until``."""
    dup_stmt = (
        select(Payment.id)
        .where(Payment.provider == "tribute", Payment.external_id == external_id)
        .limit(1)
    )
    if (await session.scalars(dup_stmt)).first() is not None:
        return TributeWebhookAck(ok=True, event=event_name, duplicate=True)

    user = await require_user_by_telegram_id(session, int(telegram_user_id))

    dup_stmt2 = (
        select(Payment.id)
        .where(Payment.provider == "tribute", Payment.external_id == external_id)
        .limit(1)
    )
    if (await session.scalars(dup_stmt2)).first() is not None:
        return TributeWebhookAck(ok=True, event=event_name, duplicate=True)

    amount_decimal = _amount_from_minor_units(int(amount_minor))
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
            external_id=external_id,
        ),
    )
    session.add(
        Task(
            task_type="notify_payment",
            user_id=int(user.id),
            referee_id=None,
            bonus_days=accumulated_bonus_days if accumulated_bonus_days > 0 else None,
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

    ext = f"sub:{int(p.subscription_id)}:{_expires_at_iso_compact(p.expires_at)}"

    return await _commit_tribute_paid_months(
        session,
        settings,
        telegram_user_id=int(p.telegram_user_id),
        months=months,
        amount_minor=int(p.price),
        external_id=ext,
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

    months = _months_from_digital_product_payload(p)
    if months is None:
        log.warning(
            "Tribute new_digital_product: нет срока (поля months/period или доп. ключи в payload; "
            "product_id=%s purchase_id=%s product_name=%r) — игнор",
            p.product_id,
            p.purchase_id,
            (p.product_name or "")[:120],
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    if p.telegram_user_id is None:
        log.warning(
            "Tribute new_digital_product: telegram_user_id отсутствует (purchase_id=%s) — игнор",
            p.purchase_id,
        )
        return TributeWebhookAck(ok=True, event=event_name, duplicate=False)

    ext = f"dp:{int(p.purchase_id)}"

    return await _commit_tribute_paid_months(
        session,
        settings,
        telegram_user_id=int(p.telegram_user_id),
        months=months,
        amount_minor=int(p.amount),
        external_id=ext,
        payment_kind="one_time",
        event_name=event_name,
    )


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


async def _handle_digital_product_refunded(*, payload: dict[str, Any]) -> TributeWebhookAck:
    log.info(
        "Tribute digital_product_refunded: payload keys=%s — запись в payments не меняется (откат доступа вручную)",
        list(payload.keys()) if isinstance(payload, dict) else type(payload),
    )
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
        _log_tribute_webhook_incoming(body_obj)
        log.info("Tribute webhook: тестовое событие test_event=%r", body_obj.get("test_event"))
        te = body_obj.get("test_event")
        return TributeWebhookAck(ok=True, event=str(te) if te is not None else "test_event", duplicate=False)

    _log_tribute_webhook_incoming(body_obj)
    env = _TributeWebhookEnvelope.model_validate(body_obj)
    return await process_tribute_webhook_event(
        session,
        settings=settings,
        name=env.name,
        payload=env.payload,
        log_incoming=False,
    )


async def process_tribute_webhook_event(
    session: AsyncSession,
    *,
    settings: Settings,
    name: str,
    payload: dict[str, Any],
    log_incoming: bool = True,
) -> TributeWebhookAck:
    """Диспетчер по ``name``. Используется и реальным webhook'ом, и тестовым эндпоинтом."""
    if log_incoming:
        _log_tribute_webhook_incoming({"name": name, "payload": payload})
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
    log.info("Tribute webhook: неизвестное событие name=%r — игнор", n)
    return TributeWebhookAck(ok=True, event=n or None, duplicate=False)
