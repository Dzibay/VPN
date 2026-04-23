"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import ReadonlySessionDep
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)

router = APIRouter(tags=["subscription"])


@router.get(
    "/sub/{token}",
    response_model=SubscriptionPayload,
    summary="Подписка (JSON): узлы, vless:// и Base64 для импорта",
)
async def subscription_by_token(token: str, session: ReadonlySessionDep) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    if not user_has_active_subscription(user):
        return SubscriptionPayload(
            valid_until=user.subscription_until,
            subscription_active=False,
            servers=[],
            vless_uris=[],
            subscription_base64="",
        )

    rows = await run_in_threadpool(subscription_servers_after_prometheus_sync)
    return build_subscription_payload(user, rows)


@router.get(
    "/sub/{token}/raw",
    summary="Тело подписки как text/plain (только Base64) — для v2rayNG, Nekoray и др.",
    response_class=Response,
)
async def subscription_base64_raw(token: str, session: ReadonlySessionDep) -> Response:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    if not user_has_active_subscription(user):
        return Response(content="", media_type="text/plain; charset=utf-8")

    rows = await run_in_threadpool(subscription_servers_after_prometheus_sync)
    payload = build_subscription_payload(user, rows)
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
    )
