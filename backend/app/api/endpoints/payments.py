"""Платежи: публичный webhook Tribute (Digital Product)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.config import settings
from app.core.dependencies import SessionDep
from app.domain.models.payments import TributeWebhookAck
from app.domain.services.tribute_service import process_tribute_webhook_raw_body

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/tribute/webhook",
    response_model=TributeWebhookAck,
    summary="Webhook Tribute (Digital Product): new_digital_product / digital_product_refund",
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
