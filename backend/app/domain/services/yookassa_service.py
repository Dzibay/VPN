"""ЮKassa: создание платежа (redirect) и webhook payment.succeeded."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError
from app.domain.tenant.project_context import get_current_project
from app.domain.models.payments import (
    PaymentWebhookAck,
    SitePaymentTariffItem,
    SitePaymentTariffsResponse,
    YookassaCheckoutResponse,
)
from app.domain.public_urls import public_spa_base_url
from app.domain.services.payment_service import (
    PaymentIngestParsed,
    ingest_provider_payment,
    net_amount_from_yookassa_payment_obj,
)
from app.infrastructure.persistence.models.project_tariff import ProjectTariff

log = logging.getLogger("app.yookassa_service")

_YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


def _require_yookassa_credentials(settings: Settings) -> tuple[str, str]:
    """Per-project (projects.yookassa_*) с fallback на глобальный settings.yookassa_*."""
    project = get_current_project()
    if project is not None:
        p_shop = (project.yookassa_shop_id or "").strip()
        p_secret = (project.yookassa_secret_key or "").strip()
        if p_shop and p_secret:
            return p_shop, p_secret
    shop_id = (settings.yookassa_shop_id or "").strip()
    secret = (settings.yookassa_secret_key or "").strip()
    if not shop_id or not secret:
        raise ServiceUnavailableError(
            detail="YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы: оплата на сайте отключена",
        )
    return shop_id, secret


def _current_project_id() -> int:
    project = get_current_project()
    return int(project.id) if project is not None else 1


async def yookassa_tariffs_public_response(session: AsyncSession) -> SitePaymentTariffsResponse:
    rows = (
        await session.execute(
            select(ProjectTariff)
            .where(
                ProjectTariff.project_id == _current_project_id(),
                ProjectTariff.provider == "yookassa",
                ProjectTariff.is_active.is_(True),
                ProjectTariff.months > 0,
                ProjectTariff.amount > 0,
            )
            .order_by(ProjectTariff.sort_order, ProjectTariff.months)
        )
    ).scalars().all()
    return SitePaymentTariffsResponse(
        tariffs=[
            SitePaymentTariffItem(
                months=int(row.months),
                price=int(row.amount),
                name=row.name or f"{int(row.months)} мес",
            )
            for row in rows
        ],
    )


async def _find_tariff(session: AsyncSession, months: int) -> tuple[int, str, Decimal] | None:
    row = (
        await session.execute(
            select(ProjectTariff)
            .where(
                ProjectTariff.project_id == _current_project_id(),
                ProjectTariff.provider == "yookassa",
                ProjectTariff.is_active.is_(True),
                ProjectTariff.months == int(months),
                ProjectTariff.amount > 0,
            )
            .limit(1)
        )
    ).scalars().first()
    if row is not None:
        return int(row.months), row.name or f"{int(row.months)} мес", Decimal(row.amount).quantize(Decimal("0.01"))
    return None


def _yookassa_return_url_for_path(settings: Settings, *, path: str, env_override: str) -> str:
    """ЮKassa требует абсолютный URL; относительный путь приведёт к ошибке create payment."""
    explicit = (env_override or "").strip()
    url = explicit
    if not url:
        base = public_spa_base_url(settings)
        if base:
            url = f"{base.rstrip('/')}{path}"
    if not url.lower().startswith(("http://", "https://")):
        raise ServiceUnavailableError(
            detail=(
                "Задайте SITE_ADDRESS (публичный домен) или YOOKASSA_RETURN_URL "
                f"(полный https://…{path}) для redirect после оплаты"
            ),
        )
    return url


def yookassa_return_url(settings: Settings) -> str:
    """Per-project override (projects.yookassa_return_url) с fallback на settings.yookassa_return_url."""
    project = get_current_project()
    override = ""
    if project is not None and project.yookassa_return_url:
        override = project.yookassa_return_url
    elif settings.yookassa_return_url:
        override = settings.yookassa_return_url
    return _yookassa_return_url_for_path(
        settings,
        path="/cabinet/pay/return",
        env_override=override,
    )


def yookassa_bot_return_url(settings: Settings) -> str:
    return _yookassa_return_url_for_path(
        settings,
        path="/cabinet/pay/return/bot",
        env_override="",
    )


async def create_yookassa_checkout(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    months: int,
    return_target: Literal["site", "bot"] = "site",
) -> YookassaCheckoutResponse:
    """Создать платёж в ЮKassa и вернуть URL для редиректа (зачисление — в webhook)."""
    shop_id, secret = _require_yookassa_credentials(settings)
    tariff = await _find_tariff(session, months)
    if tariff is None:
        raise BadRequestError(detail="Тариф с таким сроком недоступен")

    term_months, label, amount = tariff
    value_str = f"{amount:.2f}"

    body: dict[str, Any] = {
        "amount": {"value": value_str, "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": (
                yookassa_bot_return_url(settings)
                if return_target == "bot"
                else yookassa_return_url(settings)
            ),
        },
        "description": f"VPN — {label}",
        "metadata": {
            "user_id": str(int(user_id)),
            "months": str(int(term_months)),
        },
    }

    idempotence_key = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _YOOKASSA_API,
            json=body,
            auth=(shop_id, secret),
            headers={"Idempotence-Key": idempotence_key, "Content-Type": "application/json"},
        )

    if resp.status_code >= 400:
        log.warning("ЮKassa create payment HTTP %s: %s", resp.status_code, resp.text[:500])
        raise BadRequestError(detail="Не удалось создать платёж в ЮKassa")

    data = resp.json()
    yk_id = str(data.get("id") or "")
    confirmation = data.get("confirmation") if isinstance(data.get("confirmation"), dict) else {}
    confirmation_url = str(confirmation.get("confirmation_url") or "").strip()
    if not yk_id or not confirmation_url:
        log.warning("ЮKassa: неожиданный ответ create: %s", json.dumps(data)[:500])
        raise BadRequestError(detail="Некорректный ответ ЮKassa")

    return YookassaCheckoutResponse(
        confirmation_url=confirmation_url,
        yookassa_payment_id=yk_id,
    )


async def _fetch_yookassa_payment(
    settings: Settings,
    *,
    payment_id: str,
) -> dict[str, Any] | None:
    shop_id, secret = _require_yookassa_credentials(settings)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_YOOKASSA_API}/{payment_id}",
            auth=(shop_id, secret),
        )
    if resp.status_code >= 400:
        log.warning("ЮKassa GET payment %s HTTP %s", payment_id, resp.status_code)
        return None
    obj = resp.json()
    return obj if isinstance(obj, dict) else None


async def _parse_yookassa_succeeded(
    session: AsyncSession, *, payment_obj: dict[str, Any]
) -> PaymentIngestParsed | None:
    status = (payment_obj.get("status") or "").strip()
    if status != "succeeded":
        return None

    metadata = payment_obj.get("metadata")
    if not isinstance(metadata, dict):
        return None

    user_id_raw = metadata.get("user_id")
    months_raw = metadata.get("months")
    try:
        user_id = int(user_id_raw)
        months = int(months_raw)
    except (TypeError, ValueError):
        return None

    if user_id < 1 or months < 1:
        return None

    tariff = await _find_tariff(session, months)
    if tariff is None:
        log.warning("ЮKassa: неизвестный months=%s в metadata платежа %s", months, payment_obj.get("id"))
        return None

    _term_months, _label, expected_amount = tariff

    amount_obj = payment_obj.get("amount")
    if isinstance(amount_obj, dict) and amount_obj.get("value") is not None:
        try:
            amount = Decimal(str(amount_obj["value"])).quantize(Decimal("0.01"))
        except Exception:
            amount = Decimal("0")
    else:
        amount = Decimal("0")

    if amount <= 0 or amount != expected_amount:
        log.warning(
            "ЮKassa: сумма %s не совпадает с тарифом %s мес (ожидалось %s), payment_id=%s",
            amount,
            months,
            expected_amount,
            payment_obj.get("id"),
        )
        return None

    net_amount = net_amount_from_yookassa_payment_obj(payment_obj)
    if net_amount is None:
        log.warning(
            "ЮKassa: нет income_amount в платеже %s — net_amount = gross",
            payment_obj.get("id"),
        )
        net_amount = amount
    elif net_amount <= 0 or net_amount > amount:
        log.warning(
            "ЮKassa: некорректный income_amount %s (gross %s), payment_id=%s",
            net_amount,
            amount,
            payment_obj.get("id"),
        )
        return None

    paid_at: datetime | None = None
    created_at_raw = payment_obj.get("captured_at") or payment_obj.get("created_at")
    if isinstance(created_at_raw, str) and created_at_raw.strip():
        try:
            paid_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except ValueError:
            paid_at = None

    event = "payment.succeeded"
    provider_webhook = {"event": event, "object": payment_obj}

    return PaymentIngestParsed(
        provider="yookassa",
        payment_kind="one_time",
        amount=amount,
        net_amount=net_amount,
        months=months,
        provider_webhook=provider_webhook,
        fulfill=True,
        skip_reason=None,
        user_id=user_id,
        created_at=paid_at,
        event=event,
    )


async def process_yookassa_webhook_raw_body(
    session: AsyncSession,
    *,
    settings: Settings,
    raw_body: bytes,
) -> PaymentWebhookAck:
    try:
        body_obj: Any = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BadRequestError(detail="Некорректный JSON тела webhook") from None

    if not isinstance(body_obj, dict):
        raise BadRequestError(detail="Ожидается JSON-объект")

    event = (body_obj.get("event") or "").strip()
    obj = body_obj.get("object")
    if event != "payment.succeeded" or not isinstance(obj, dict):
        return PaymentWebhookAck(ok=True, event=event or "ignored", fulfilled=False, skip_reason="ignored")

    payment_id = str(obj.get("id") or "").strip()
    if not payment_id:
        return PaymentWebhookAck(ok=True, event=event, fulfilled=False, skip_reason="no_payment_id")

    verified = await _fetch_yookassa_payment(settings, payment_id=payment_id)
    if verified is None:
        return PaymentWebhookAck(ok=True, event=event, fulfilled=False, skip_reason="verify_failed")

    parsed = await _parse_yookassa_succeeded(session, payment_obj=verified)
    if parsed is None:
        return PaymentWebhookAck(ok=True, event=event, fulfilled=False, skip_reason="not_succeeded")

    return await ingest_provider_payment(session, settings, parsed=parsed)
