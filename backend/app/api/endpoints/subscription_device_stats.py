"""Сводка по устройствам подписки (User-Agent) — JWT admin или manager."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import ReadonlySessionDep, require_referrals_staff
from app.domain.models.subscription_device_stats import (
    SubscriptionDeviceUserAgentStatsItem,
    SubscriptionDeviceUserAgentStatsResponse,
)
from app.domain.services.subscription_device_stats_service import (
    admin_stats_subscription_devices_by_user_agent,
)

router = APIRouter(
    prefix="/admin/subscription-devices",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "/stats-by-user-agent",
    response_model=SubscriptionDeviceUserAgentStatsResponse,
    summary="Статистика по UA (до первого /) и ОС: пользователи с устройством и с трафиком",
)
async def get_subscription_device_stats_by_user_agent(
    session: ReadonlySessionDep,
) -> SubscriptionDeviceUserAgentStatsResponse:
    raw = await admin_stats_subscription_devices_by_user_agent(session)
    return SubscriptionDeviceUserAgentStatsResponse(
        items=[SubscriptionDeviceUserAgentStatsItem.model_validate(r) for r in raw],
    )
