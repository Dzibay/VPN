"""Платежи: webhook Tribute и ЮKassa."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.config import settings
from app.core.dependencies import SessionDep, require_telegram_bot_api_secret
from app.domain.models.payments import (
    PaymentWebhookAck,
    SitePaymentTariffsResponse,
    TributeWebhookAck,
    TributeWebhookTestBody,
)
from app.domain.services.tribute_service import (
    process_tribute_webhook_event,
    process_tribute_webhook_raw_body,
)
from app.domain.services.yookassa_service import (
    process_yookassa_webhook_raw_body,
    yookassa_tariffs_public_response,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get(
    "/tariffs",
    response_model=SitePaymentTariffsResponse,
    summary="Тарифы разовой оплаты (app/data/yookassa_tariffs.json)",
)
async def payment_tariffs() -> SitePaymentTariffsResponse:
    return yookassa_tariffs_public_response()


@router.post(
    "/tribute/webhook",
    response_model=TributeWebhookAck,
    summary="Webhook Tribute: подписка (new/renewed_subscription), цифровой товар (new_digital_product), refund (лог)",
    description=(),
)
async def tribute_webhook_ep(
    request: Request,
    session: SessionDep,
    trbt_signature: Annotated[str | None, Header(alias="trbt-signature")] = None,
) -> TributeWebhookAck:
    raw = await request.body()
    return await process_tribute_webhook_raw_body(
        session,
        settings=settings,
        raw_body=raw,
        trbt_signature=trbt_signature,
    )


@router.post(
    "/tribute/webhook-test",
    response_model=TributeWebhookAck,
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Тестовый прогон Tribute-webhook без HMAC (X-Telegram-Bot-Secret вместо trbt-signature)",
    description=(),
)
async def tribute_webhook_test_ep(
    session: SessionDep,
    body: TributeWebhookTestBody,
) -> TributeWebhookAck:
    return await process_tribute_webhook_event(
        session,
        settings=settings,
        name=body.name,
        payload=body.payload.model_dump(mode="json"),
    )


@router.post(
    "/yookassa/webhook",
    response_model=PaymentWebhookAck,
    summary="Webhook ЮKassa: payment.succeeded (тело проверяется повторным GET платежа)",
    description=(),
)
async def yookassa_webhook_ep(
    request: Request,
    session: SessionDep,
) -> PaymentWebhookAck:
    raw = await request.body()
    return await process_yookassa_webhook_raw_body(
        session,
        settings=settings,
        raw_body=raw,
    )
