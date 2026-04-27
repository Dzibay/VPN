"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).

Открытие клиента: GET /sub/{token}/open/{client} — client из белого списка в
app.domain.subscription_open_apps (например happ → happ://add/https://…/sub/{token}).
"""

from __future__ import annotations

import html
import json

from fastapi import APIRouter, HTTPException, Path, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.api.deps import ReadonlySessionDep
from app.core.config import settings
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.domain.subscription_open_apps import (
    SubscriptionOpenApp,
    get_subscription_open_app,
    list_subscription_open_app_slugs,
)
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)

router = APIRouter(tags=["public"])

_OPEN_APPS_DOC = ", ".join(list_subscription_open_app_slugs())


def _resolve_public_base(request: Request, configured_base: str) -> str:
    raw = (configured_base or "").strip().rstrip("/")
    if raw:
        return raw
    return str(request.base_url).rstrip("/")


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


def _client_landing_page(
    request: Request, user: User, app: SubscriptionOpenApp
) -> HTMLResponse:
    base = _resolve_public_base(request, settings.subscription_public_base_url)
    subscription_url = f"{base}/sub/{user.token}"
    deeplink = app.build_deeplink(subscription_url)
    title = f"Подключение {app.display_name}"
    button = f"Открыть в {app.display_name}"
    content = _open_app_page(title, None, deeplink, button)
    return HTMLResponse(content=content)


def _open_app_page(
    title: str,
    paragraph: str | None,
    deeplink: str | None,
    button_text: str,
) -> str:
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
    if deeplink:
        js_u = json.dumps(deeplink)
        chunks.append(f"<script>try{{location.replace({js_u});}}catch(e){{}}</script>")
        chunks.append(f"<p><a href={js_u}>{html.escape(button_text)}</a></p>")
        chunks.append(
            "<p style=\"color:#555;font-size:.9rem\">Если приложение не открылось, нажмите кнопку выше.</p>"
        )
    chunks.append("</body></html>")
    return "".join(chunks)


@router.get(
    "/sub/{token}/open/{client}",
    summary=f"Открыть подписку в приложении (client: {_OPEN_APPS_DOC})",
    response_class=HTMLResponse,
)
async def subscription_open_in_app(
    request: Request,
    session: ReadonlySessionDep,
    token: str,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Доступно: {_OPEN_APPS_DOC}",
    ),
) -> HTMLResponse:
    app = get_subscription_open_app(client)
    if app is None:
        allowed = ", ".join(list_subscription_open_app_slugs()) or "—"
        return HTMLResponse(
            content=_open_app_page(
                "Неизвестное приложение",
                f"Укажите client из списка: {allowed}.",
                None,
                "",
            ),
            status_code=404,
        )

    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        return HTMLResponse(
            content=_open_app_page(
                "Ссылка недействительна",
                "Проверьте ссылку или получите новую в боте / личном кабинете.",
                None,
                "",
            ),
            status_code=404,
        )
    if not user_has_active_subscription(user):
        return HTMLResponse(
            content=_open_app_page(
                "Подписка не активна",
                "Продлите подписку и попробуйте снова.",
                None,
                "",
            ),
        )
    return _client_landing_page(request, user, app)


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
