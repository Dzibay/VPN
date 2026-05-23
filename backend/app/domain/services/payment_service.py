"""Универсальная логика платежей: зачисление подписки и ingest после webhook провайдера."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.request_subject import bind_request_subject_user
from app.core.time import moscow_today
from app.domain.models.payments import PaymentWebhookAck
from app.domain.referrals.payment_tasks import apply_referral_bonus_on_payment
from app.domain.referrals.task_bonus_days import sum_referral_bonus_days_pending_activation
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.payment_service")

DAYS_PER_MONTH = 31

PaymentProvider = Literal["manual", "tribute", "yookassa"]
PaymentKind = Literal["subscription", "one_time"]

_PAID_TRIBUTE_SUBSCRIPTION_EVENTS = frozenset({"new_subscription", "renewed_subscription"})


@dataclass(frozen=True)
class PaymentIngestParsed:
    """Нормализованный платёж после разбора webhook провайдера."""

    provider: PaymentProvider
    payment_kind: PaymentKind
    amount: Decimal
    months: int
    provider_webhook: dict[str, Any]
    fulfill: bool
    skip_reason: str | None = None
    user_id: int | None = None
    telegram_user_id: int | None = None
    created_at: datetime | None = None
    event: str | None = None


def amount_from_minor_units(amount_minor: int) -> Decimal:
    return (Decimal(int(amount_minor)) * Decimal("0.01")).quantize(Decimal("0.01"))


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: datetime) -> str:
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")


def extend_subscription_until(base: date | None, *, days: int) -> date:
    if days < 1:
        raise ValueError("days must be >= 1")
    today = moscow_today()
    start = base if base is not None and base >= today else today
    return start + timedelta(days=days)


async def fulfill_subscription_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    months: int,
    paid_at: datetime | None,
) -> None:
    """Продление подписки, notify_payment, реферальные бонусы, снятие лимита трафика."""
    from app.domain.subscription.traffic_limit import (
        clear_traffic_limit_after_payment,
        enqueue_xray_clients_sync_for_access_change,
    )

    paid_days = int(months) * DAYS_PER_MONTH
    accumulated_bonus_days = await sum_referral_bonus_days_pending_activation(
        session,
        user_id=int(user.id),
    )
    total_days = paid_days + accumulated_bonus_days
    user.subscription_until = extend_subscription_until(user.subscription_until, days=total_days)

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
    if await clear_traffic_limit_after_payment(session, user):
        enqueue_xray_clients_sync_for_access_change()


async def find_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == int(telegram_id)).limit(1)
    return (await session.scalars(stmt)).first()


async def find_duplicate_payment_id(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    provider_webhook: dict[str, Any],
) -> int | None:
    """Идемпотентность: уже обработанный webhook того же провайдера."""
    if provider == "tribute":
        name = (provider_webhook.get("name") or "").strip()
        payload = provider_webhook.get("payload")
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
                    Payment.provider_webhook["name"].astext == name,
                    Payment.provider_webhook["payload"]["purchase_id"].as_integer()
                    == int(purchase_id),
                )
                .limit(1)
            )
        elif name in _PAID_TRIBUTE_SUBSCRIPTION_EVENTS:
            subscription_id = payload.get("subscription_id")
            expires_at = payload.get("expires_at")
            if subscription_id is None or expires_at is None:
                return None
            stmt = (
                select(Payment.id)
                .where(
                    Payment.provider == "tribute",
                    Payment.provider_webhook["payload"]["subscription_id"].as_integer()
                    == int(subscription_id),
                    Payment.provider_webhook["payload"]["expires_at"].astext == str(expires_at),
                )
                .limit(1)
            )
        else:
            return None

        row = (await session.scalars(stmt)).first()
        return int(row) if row is not None else None

    if provider == "yookassa":
        obj = provider_webhook.get("object")
        if not isinstance(obj, dict):
            return None
        payment_id = obj.get("id")
        if not payment_id:
            return None
        stmt = (
            select(Payment.id)
            .where(
                Payment.provider == "yookassa",
                Payment.provider_webhook["object"]["id"].astext == str(payment_id),
            )
            .limit(1)
        )
        row = (await session.scalars(stmt)).first()
        return int(row) if row is not None else None

    return None


async def _resolve_user_for_fulfillment(
    session: AsyncSession,
    *,
    user_id: int | None,
    telegram_user_id: int | None,
) -> User | None:
    if user_id is not None:
        return await session.get(User, int(user_id))
    if telegram_user_id is not None:
        return await find_user_by_telegram_id(session, int(telegram_user_id))
    return None


async def create_staff_manual_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    months: int,
    amount: Decimal,
    payment_kind: PaymentKind,
    created_at: datetime | None = None,
) -> Payment:
    """Ручное начисление из админки: ``provider=manual``, без webhook провайдера."""
    user = await session.get(User, int(user_id))
    if user is None:
        raise LookupError("user_not_found")

    paid_at = ensure_utc(created_at) if created_at is not None else datetime.now(timezone.utc)
    amount_q = Decimal(amount).quantize(Decimal("0.01"))

    payment = Payment(
        user_id=int(user_id),
        amount=amount_q,
        months=int(months),
        provider="manual",
        payment_kind=payment_kind,
        provider_webhook=None,
        created_at=paid_at,
    )
    session.add(payment)
    await session.flush()

    bind_request_subject_user(int(user_id), source="staff_manual_payment")
    await fulfill_subscription_payment(
        session,
        settings,
        user=user,
        months=int(months),
        paid_at=paid_at,
    )
    await session.flush()
    log.info(
        "manual: платёж %s, user_id=%s, months=%s, amount=%s",
        payment.id,
        user_id,
        months,
        amount_q,
    )
    return payment


async def ingest_provider_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    parsed: PaymentIngestParsed,
) -> PaymentWebhookAck:
    """Запись в payments и опциональное зачисление подписки (общий путь для всех провайдеров)."""
    event_name = (parsed.event or "").strip() or parsed.provider

    dup_id = await find_duplicate_payment_id(
        session,
        provider=parsed.provider,
        provider_webhook=parsed.provider_webhook,
    )
    if dup_id is not None:
        skip_reason = parsed.skip_reason or "duplicate"
        existing = await session.get(Payment, int(dup_id))
        already_fulfilled = (
            existing is not None
            and existing.user_id is not None
            and int(existing.months) >= 1
            and parsed.fulfill
        )
        log.warning(
            "%s %s: дубликат webhook (payment_id=%s, already_fulfilled=%s)",
            parsed.provider,
            event_name,
            dup_id,
            already_fulfilled,
        )
        return PaymentWebhookAck(
            ok=True,
            event=event_name,
            duplicate=True,
            payment_id=dup_id,
            fulfilled=already_fulfilled,
            skip_reason=skip_reason if not already_fulfilled else None,
        )

    paid_at = ensure_utc(parsed.created_at) if parsed.created_at is not None else None
    payment_user_id: int | None = None
    fulfilled = False
    skip_reason = parsed.skip_reason

    payment = Payment(
        user_id=None,
        amount=parsed.amount,
        months=max(0, int(parsed.months)),
        provider=parsed.provider,
        payment_kind=parsed.payment_kind,
        provider_webhook=parsed.provider_webhook,
        **({"created_at": paid_at} if paid_at is not None else {}),
    )

    try:
        async with session.begin_nested():
            session.add(payment)
            await session.flush()
    except IntegrityError:
        existing_id = await find_duplicate_payment_id(
            session,
            provider=parsed.provider,
            provider_webhook=parsed.provider_webhook,
        )
        if existing_id is None:
            raise
        skip_reason = parsed.skip_reason or "duplicate"
        return PaymentWebhookAck(
            ok=True,
            event=event_name,
            duplicate=True,
            payment_id=existing_id,
            fulfilled=False,
            skip_reason=skip_reason,
        )

    payment_id = int(payment.id)

    can_fulfill = (
        parsed.fulfill
        and parsed.months >= 1
        and (parsed.user_id is not None or parsed.telegram_user_id is not None)
    )
    if can_fulfill:
        user = await _resolve_user_for_fulfillment(
            session,
            user_id=parsed.user_id,
            telegram_user_id=parsed.telegram_user_id,
        )
        if user is None:
            skip_reason = "user_not_found"
            log.warning(
                "%s %s: пользователь не найден (user_id=%s telegram_id=%s) — платёж %s без продления",
                parsed.provider,
                event_name,
                parsed.user_id,
                parsed.telegram_user_id,
                payment_id,
            )
        else:
            payment_user_id = int(user.id)
            payment.user_id = payment_user_id
            bind_request_subject_user(
                payment_user_id,
                source=f"{parsed.provider}_webhook",
            )
            await fulfill_subscription_payment(
                session,
                settings,
                user=user,
                months=int(parsed.months),
                paid_at=paid_at,
            )
            fulfilled = True
            skip_reason = None
            log.info(
                "%s %s: платёж %s, user_id=%s, months=%s",
                parsed.provider,
                event_name,
                payment_id,
                payment_user_id,
                parsed.months,
            )
    elif parsed.fulfill and skip_reason is None:
        skip_reason = "incomplete_payload"

    await session.flush()

    return PaymentWebhookAck(
        ok=True,
        event=event_name,
        duplicate=False,
        payment_id=payment_id,
        fulfilled=fulfilled,
        skip_reason=skip_reason,
    )
