"""Ответы админ-API: сводка по User-Agent зарегистрированных устройств подписки."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubscriptionDeviceUserAgentStatsItem(BaseModel):
    user_agent: str = Field(description="Значение User-Agent с устройства (как в subscription_devices)")
    connected_users: int = Field(
        ge=0,
        description="Число разных пользователей, у которых есть устройство с этим User-Agent",
    )
    users_with_traffic: int = Field(
        ge=0,
        description="Из них пользователей с ненулевой суммой up+down по user_server_traffic",
    )


class SubscriptionDeviceUserAgentStatsResponse(BaseModel):
    items: list[SubscriptionDeviceUserAgentStatsItem]
