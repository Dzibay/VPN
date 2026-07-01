"""Платежи: webhook Tribute и ЮKassa (multi-tenant по URL slug)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, SessionDep, require_telegram_bot_api_secret
from app.core.exceptions import NotFoundError
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
from app.domain.tenant.project_cache import get_project_by_id, get_project_by_slug
from app.domain.tenant.project_context import (
    reset_current_project,
    set_current_project,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get(
    "/tariffs",
    response_model=SitePaymentTariffsResponse,
    summary="Тарифы разовой оплаты текущего проекта",
)
async def payment_tariffs(session: ReadonlySessionDep) -> SitePaymentTariffsResponse:
    return await yookassa_tariffs_public_response(session)


async def _resolve_webhook_project(request: Request, slug: str | None):
    """Multi-tenant резолвинг проекта для webhook: по slug из URL, fallback на Host, затем на id=1."""
    if slug:
        project = await get_project_by_slug(slug)
        if project is None:
            raise NotFoundError(detail=f"Проект '{slug}' не найден")
        return project
    project = getattr(request.state, "project", None)
    if project is not None:
        return project
    fallback = await get_project_by_id(1)
    if fallback is None:
        raise NotFoundError(detail="Дефолтный проект не сконфигурирован")
    return fallback


@router.post(
    "/tribute/webhook",
    response_model=TributeWebhookAck,
    summary="Webhook Tribute (legacy, без slug — резолвится по Host / project_id=1)",
    description=(),
)
async def tribute_webhook_ep(
    request: Request,
    session: SessionDep,
    trbt_signature: Annotated[str | None, Header(alias="trbt-signature")] = None,
) -> TributeWebhookAck:
    project = await _resolve_webhook_project(request, None)
    token = set_current_project(project)
    try:
        raw = await request.body()
        return await process_tribute_webhook_raw_body(
            session,
            settings=settings,
            raw_body=raw,
            trbt_signature=trbt_signature,
        )
    finally:
        reset_current_project(token)


@router.post(
    "/tribute/webhook/{project_slug}",
    response_model=TributeWebhookAck,
    summary="Webhook Tribute для проекта по slug (multi-tenant)",
    description=(),
)
async def tribute_webhook_by_slug_ep(
    project_slug: str,
    request: Request,
    session: SessionDep,
    trbt_signature: Annotated[str | None, Header(alias="trbt-signature")] = None,
) -> TributeWebhookAck:
    project = await _resolve_webhook_project(request, project_slug)
    token = set_current_project(project)
    try:
        raw = await request.body()
        return await process_tribute_webhook_raw_body(
            session,
            settings=settings,
            raw_body=raw,
            trbt_signature=trbt_signature,
        )
    finally:
        reset_current_project(token)


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
    summary="Webhook ЮKassa (legacy, без slug — резолвится по Host / project_id=1)",
    description=(),
)
async def yookassa_webhook_ep(
    request: Request,
    session: SessionDep,
) -> PaymentWebhookAck:
    project = await _resolve_webhook_project(request, None)
    token = set_current_project(project)
    try:
        raw = await request.body()
        return await process_yookassa_webhook_raw_body(
            session,
            settings=settings,
            raw_body=raw,
        )
    finally:
        reset_current_project(token)


@router.post(
    "/yookassa/webhook/{project_slug}",
    response_model=PaymentWebhookAck,
    summary="Webhook ЮKassa для проекта по slug (multi-tenant)",
    description=(),
)
async def yookassa_webhook_by_slug_ep(
    project_slug: str,
    request: Request,
    session: SessionDep,
) -> PaymentWebhookAck:
    project = await _resolve_webhook_project(request, project_slug)
    token = set_current_project(project)
    try:
        raw = await request.body()
        return await process_yookassa_webhook_raw_body(
            session,
            settings=settings,
            raw_body=raw,
        )
    finally:
        reset_current_project(token)
