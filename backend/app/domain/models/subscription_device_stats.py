"""Ответы админ-API: сводка по User-Agent зарегистрированных устройств подписки."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubscriptionDeviceUserAgentStatsItem(BaseModel):
    user_agent: str = Field(
        description="User-Agent до первого «/» (например Happ из Happ/2.9/Windows)",
    )
    os: str = Field(
        description="x-device-os с устройства; пустая строка, если не передавался",
    )
    connected_users: int = Field(
        ge=0,
        description="Число разных пользователей, у которых есть устройство с этой парой UA+OS",
    )
    users_with_traffic: int = Field(
        ge=0,
        description="Из них пользователей с ненулевой суммой up+down по user_server_traffic",
    )
    users_over_100mb: int = Field(
        ge=0,
        description="Из них пользователей с суммарным трафиком больше 100 MiB (up+down)",
    )
    active_users_today: int = Field(
        ge=0,
        description="Из них пользователей с ненулевым трафиком за текущий день UTC",
    )


class SubscriptionDeviceUserAgentStatsResponse(BaseModel):
    items: list[SubscriptionDeviceUserAgentStatsItem]
