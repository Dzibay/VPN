"""Tribute: webhook подписки и разовой цифровой покупки.

Ссылки/цены для UI берутся из ``project_tariffs`` текущего проекта.

Каждый HTTP webhook пишется в ``user_http_request_traces`` (см. ``http_audit_always_persist_for_path``).
Зачисление подписки — через :func:`app.domain.services.payment_service.ingest_provider_payment`.

HMAC: заголовок ``trbt-signature``, ключ ``TRIBUTE_API_KEY``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import constants
from app.config import Settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError, UnauthorizedError
from app.domain.tenant.project_context import get_current_project
from app.domain.models.payments import (
    PaymentWebhookAck,
    TributePaymentOptionItem,
    TributePaymentsLinksResponse,
    TributeWebhookAck,
)
from app.domain.services.payment_service import (
    PaymentIngestParsed,
    amount_from_minor_units,
    compute_tribute_net_amount,
    ingest_provider_payment,
)
from app.infrastructure.persistence.models.project_tariff import ProjectTariff
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.tribute_service")

_PAID_SUBSCRIPTION_EVENTS = frozenset({"new_subscription", "renewed_subscription"})
_PAID_DIGITAL_EVENTS = frozenset({"new_digital_product"})


def _current_project_id() -> int:
    project = get_current_project()
    return int(project.id) if project is not None else 1


async def tribute_payments_links_public_response(session: AsyncSession) -> TributePaymentsLinksResponse:
    rows = (
        await session.execute(
            select(ProjectTariff)
            .where(
                ProjectTariff.project_id == _current_project_id(),
                ProjectTariff.provider == "tribute",
                ProjectTariff.is_active.is_(True),
                ProjectTariff.external_link.is_not(None),
            )
            .order_by(ProjectTariff.sort_order, ProjectTariff.months)
        )
    ).scalars().all()
    items: list[TributePaymentOptionItem] = []
    for row in rows:
        link = (row.external_link or "").strip()
        if not link:
            continue
        is_recurring = (row.kind or "").strip().lower() == "recurring" or int(row.months) <= 0
        items.append(
            TributePaymentOptionItem(
                months=None if is_recurring else int(row.months),
                price=None if is_recurring or row.amount <= 0 else int(row.amount),
                tg_link=row.external_tg_link,
                web_link=link,
                name=row.name or ("Подписка" if is_recurring else f"{int(row.months)} мес"),
                type="recurring" if is_recurring else "single",
            )
        )
    return TributePaymentsLinksResponse(tariffs=items)


_PERIOD_TO_MONTHS: dict[str, int] = {
    "monthly": 1,
    "quarterly": 3,
    "biannual": 6,
    "semiannual": 6,
    "half_yearly": 6,
    "yearly": 12,
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
    """Per-project ключ (projects.tribute_api_key) с fallback на глобальный settings.tribute_api_key."""
    project = get_current_project()
    if project is not None:
        project_key = (project.tribute_api_key or "").strip()
        if project_key:
            return project_key
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


def _period_to_months(period: str) -> int | None:
    return _PERIOD_TO_MONTHS.get((period or "").strip().lower())


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


def _resolve_new_digital_product_months_legacy(p: _DigitalProductPaidPayload) -> int | None:
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


async def _resolve_new_digital_product_months(
    session: AsyncSession, p: _DigitalProductPaidPayload
) -> int | None:
    direct = _resolve_new_digital_product_months_legacy(p)
    if direct is not None:
        return direct

    product_id = str(p.product_id).strip() if p.product_id is not None else ""
    product_name = (p.product_name or "").strip()
    if not product_id and not product_name:
        return None

    stmt = select(ProjectTariff).where(
        ProjectTariff.project_id == _current_project_id(),
        ProjectTariff.provider == "tribute",
        ProjectTariff.is_active.is_(True),
        ProjectTariff.months > 0,
    )
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        if product_id and str(row.external_product_id or "").strip() == product_id:
            return int(row.months)
        if product_name and (row.name or "").strip() == product_name:
            return int(row.months)
    return None


def _provider_webhook_envelope(*, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
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


async def _parse_digital_product_paid(
    session: AsyncSession, *, payload: dict[str, Any]
) -> _TributeWebhookParsed:
    try:
        p = _DigitalProductPaidPayload.model_validate(payload)
    except ValidationError:
        p = _DigitalProductPaidPayload()

    months = await _resolve_new_digital_product_months(session, p) or 0
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


def _tribute_parsed_to_ingest(
    *,
    event_name: str,
    payload: dict[str, Any],
    parsed: _TributeWebhookParsed,
) -> PaymentIngestParsed:
    gross = amount_from_minor_units(parsed.amount_minor)
    return PaymentIngestParsed(
        provider="tribute",
        payment_kind=parsed.payment_kind,
        amount=gross,
        net_amount=compute_tribute_net_amount(gross),
        months=max(0, int(parsed.months)),
        provider_webhook=_provider_webhook_envelope(event_name=event_name, payload=payload),
        fulfill=parsed.fulfill,
        skip_reason=parsed.skip_reason,
        telegram_user_id=parsed.telegram_user_id,
        created_at=parsed.created_at,
        event=event_name,
    )


async def _ingest_tribute_webhook(
    session: AsyncSession,
    settings: Settings,
    *,
    event_name: str,
    payload: dict[str, Any],
    parsed: _TributeWebhookParsed,
) -> TributeWebhookAck:
    return await ingest_provider_payment(
        session,
        settings,
        parsed=_tribute_parsed_to_ingest(
            event_name=event_name,
            payload=payload,
            parsed=parsed,
        ),
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

async def process_tribute_webhook_event(
    session: AsyncSession,
    *,
    settings: Settings,
    name: str,
    payload: dict[str, Any],
) -> PaymentWebhookAck:
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
        parsed = await _parse_digital_product_paid(session, payload=payload)
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
