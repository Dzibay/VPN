"""Сборка тестовой подписки GET /sub/test-sub (алиас основной логики /sub)."""

from __future__ import annotations

from app.domain.models.subscription import SubscriptionPayload
from app.domain.subscription.build import build_subscription_payload
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

build_test_sub_payload = build_subscription_payload

__all__ = ["build_test_sub_payload", "build_subscription_payload"]
