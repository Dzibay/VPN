"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).

Кнопка в Telegram: GET /sub/{token}/open/happ → страница с happ://add/… (и запасная ссылка).
"""

from __future__ import annotations

import html
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.api.deps import ReadonlySessionDep
from app.core.config import settings
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)

router = APIRouter(tags=["public"])


def _resolve_public_base(request: Request, configured_base: str) -> str:
    raw = (configured_base or "").strip().rstrip("/")
    if raw:
        return raw
    return str(request.base_url).rstrip("/")


def _build_happ_add_url(subscription_https_url: str) -> str:
    return "happ://add/" + quote(subscription_https_url, safe="")


async def _subscription_payload_for_token(
    token: str, session: ReadonlySessionDep
) -> SubscriptionPayload:
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


def _happ_landing_page(request: Request, user: User) -> HTMLResponse:
    base = _resolve_public_base(request, settings.subscription_public_base_url)
    subscription_url = f"{base}/sub/{user.token}"
    happ_url = _build_happ_add_url(subscription_url)
    content = _tg_page("Подключение Happ", None, happ_url)
    return HTMLResponse(content=content)


def _tg_page(title: str, paragraph: str | None = None, happ_url: str | None = None) -> str:
    chunks = [
        "<!DOCTYPE html><html lang=\"ru\"><head>",
        "<meta charset=\"utf-8\"/>",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>",
        f"<title>{html.escape(title)}</title>",
        (
            "<style>"
            "body{font-family:system-ui,sans-serif;padding:1.5rem;max-width:28rem;margin:auto;line-height:1.45}"
            "a{display:inline-block;margin-top:1rem;padding:.6rem 1rem;background:#248bda;color:#fff;"
            "border-radius:8px;text-decoration:none}"
            "</style>"
        ),
        "</head><body>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    if paragraph:
        chunks.append(f"<p>{html.escape(paragraph)}</p>")
    if happ_url:
        js_u = json.dumps(happ_url)
        chunks.append(f"<script>try{{location.replace({js_u});}}catch(e){{}}</script>")
        chunks.append(f"<p><a href={js_u}>Открыть в Happ</a></p>")
        chunks.append(
            "<p style=\"color:#555;font-size:.9rem\">Если приложение не открылось, нажмите кнопку выше.</p>"
        )
    chunks.append("</body></html>")
    return "".join(chunks)


@router.get(
    "/sub/{token}/open/happ",
    summary="Кнопка в Telegram: открыть Happ с подпиской /sub/{token}",
    response_class=HTMLResponse,
)
async def subscription_open_happ(
    request: Request,
    session: ReadonlySessionDep,
    token: str,
) -> HTMLResponse:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        return HTMLResponse(
            content=_tg_page(
                "Ссылка недействительна",
                "Проверьте ссылку или получите новую в боте / личном кабинете.",
            ),
            status_code=404,
        )
    if not user_has_active_subscription(user):
        return HTMLResponse(
            content=_tg_page(
                "Подписка не активна",
                "Продлите подписку и попробуйте снова.",
            ),
        )
    return _happ_landing_page(request, user)


@router.get(
    "/sub/{token}",
    summary="Подписка: text/plain, одна строка Base64 (v2rayNG, Nekoray и др.)",
    response_class=Response,
)
async def subscription_base64_by_token(token: str, session: ReadonlySessionDep) -> Response:
    payload = await _subscription_payload_for_token(token, session)
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
    )


@router.get(
    "/sub/{token}/json",
    response_model=SubscriptionPayload,
    summary="Подписка (JSON): узлы, vless:// и поле subscription_base64",
)
async def subscription_json_by_token(token: str, session: ReadonlySessionDep) -> SubscriptionPayload:
    return await _subscription_payload_for_token(token, session)
