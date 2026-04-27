"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{subscription_token}).

Перед выдачей списка узлов обновляется servers.load_percent из Prometheus, затем
узлы сортируются по возрастанию нагрузки (как и раньше).

- GET /sub/{subscription_token}/open/{client} — открытие в приложении; неизвестный client → 302 в /cabinet.
"""

from __future__ import annotations

import html
import json
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.api.deps import ReadonlySessionDep
from app.core.config import settings
from app.database.operations import table_select_one
from app.domain.subscription import user_has_active_subscription
from app.domain.subscription_open_apps import (
    AppStoreLinks,
    SubscriptionOpenApp,
    get_subscription_open_app,
    list_subscription_open_app_codes,
)
from app.models.user import User
from app.schemas.users import SubscriptionPayload
from app.services.subscription_delivery import (
    build_subscription_payload,
    subscription_servers_after_prometheus_sync,
)

router = APIRouter(tags=["public"])

# Имя path-параметра не «token»: иначе Swagger UI подставляет example=token и URL выглядит как /sub/token/... .
_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE = "R7k4mN9pQ2sT5vX8yZ1aB3cD6eF0gH2j"
_SUBSCRIPTION_TOKEN_PATH = Path(
    ...,
    description="Токен подписки (users.token), сегмент пути /sub/…/…",
    examples=[_SUBSCRIPTION_TOKEN_OPENAPI_EXAMPLE],
)

_OPEN_APPS_DOC = ", ".join(list_subscription_open_app_codes())

_STORE_PLATFORM_KEYS = frozenset({"windows", "android", "ios"})


def _normalize_store_platform(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    return v if v in _STORE_PLATFORM_KEYS else None


def _cabinet_redirect_url(*, extra_query: dict[str, str] | None = None) -> str:
    raw = (settings.public_cabinet_url or "").strip().rstrip("/")
    if not raw:
        path = "/cabinet"
    elif raw.startswith(("http://", "https://")):
        path = raw
    else:
        path = raw if raw.startswith("/") else f"/{raw}"
    if extra_query:
        q = urlencode(extra_query)
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}{q}"
    return path


def _resolve_public_base(request: Request, configured_base: str) -> str:
    raw = (configured_base or "").strip().rstrip("/")
    if raw:
        return raw
    return str(request.base_url).rstrip("/")


async def _subscription_payload_for_token(
    subscription_token: str, session: ReadonlySessionDep
) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": subscription_token})
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
    request: Request,
    user: User,
    app: SubscriptionOpenApp,
    *,
    store_platform: str | None = None,
) -> HTMLResponse:
    base = _resolve_public_base(request, settings.subscription_public_base_url)
    subscription_url = f"{base}/sub/{user.token}"
    deeplink = app.build_deeplink(subscription_url)
    title = f"Подключение — {app.display_name}"
    open_label = f"Открыть в {app.display_name}"
    content = _open_app_page(
        title,
        None,
        deeplink,
        open_label,
        store_links=app.store_links,
        client_display_name=app.display_name,
        store_platform=store_platform,
    )
    return HTMLResponse(content=content)


# Синхронизировать с frontend/src/style.css (токены и кнопки).
_SUBSCRIPTION_OPEN_LANDING_CSS = """
:root {
  --brand-mint: #58d68d;
  --brand-teal: #45b39d;
  --bg-glow-violet: rgba(124, 58, 237, 0.2);
  --bg-glow-mint: rgba(88, 214, 141, 0.16);
  --bg-glow-iris: rgba(99, 102, 234, 0.12);
  --accent: var(--brand-mint);
  --accent-muted: var(--brand-teal);
  --accent-soft: rgba(88, 214, 141, 0.16);
  --accent-border: rgba(88, 214, 141, 0.42);
  --on-accent: #000000;
  --text: #a8b8b0;
  --text-h: #e8f4ec;
  --muted: #6d8578;
  --bg: #020203;
  --bg-gradient:
    radial-gradient(ellipse 115% 85% at 0% -5%, var(--bg-glow-violet) 0%, transparent 52%),
    radial-gradient(ellipse 95% 75% at 100% 5%, var(--bg-glow-mint) 0%, transparent 50%),
    radial-gradient(ellipse 70% 55% at 50% 105%, var(--bg-glow-iris) 0%, transparent 55%),
    radial-gradient(ellipse 55% 45% at 75% 45%, rgba(45, 179, 157, 0.08) 0%, transparent 50%),
    linear-gradient(168deg, #03010a 0%, #040806 24%, #060a14 48%, #05030d 72%, #000000 100%);
  --surface-glass: rgba(12, 16, 14, 0.9);
  --card-border: rgba(88, 214, 141, 0.18);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.45);
  --shadow-md: 0 12px 32px rgba(0, 0, 0, 0.5);
  --focus-ring: 0 0 0 3px rgba(88, 214, 141, 0.4);
  --radius-lg: 12px;
  --sans: 'Manrope', system-ui, 'Segoe UI', sans-serif;
  --heading: 'Sora', var(--sans);
  font: 17px/1.55 var(--sans);
  color-scheme: dark;
  color: var(--text);
}
@media (max-width: 1024px) { :root { font-size: 16px; } }
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --accent: #1d9a5c;
    --accent-muted: #1a7a4a;
    --accent-soft: rgba(29, 154, 92, 0.12);
    --accent-border: rgba(29, 154, 92, 0.35);
    --on-accent: #ffffff;
    --text: #3d4a45;
    --text-h: #0a0f0d;
    --muted: #5a6a62;
    --bg-glow-violet: rgba(139, 92, 246, 0.09);
    --bg-glow-mint: rgba(88, 214, 141, 0.11);
    --bg-glow-iris: rgba(99, 102, 234, 0.06);
    --bg-gradient:
      radial-gradient(ellipse 100% 80% at 0% 0%, var(--bg-glow-violet) 0%, transparent 55%),
      radial-gradient(ellipse 90% 70% at 100% 15%, var(--bg-glow-mint) 0%, transparent 52%),
      radial-gradient(ellipse 80% 60% at 50% 100%, var(--bg-glow-iris) 0%, transparent 50%),
      linear-gradient(162deg, #faf6ff 0%, #f0f8f4 38%, #f4f0fb 70%, #f2f7f4 100%);
    --surface-glass: rgba(255, 255, 255, 0.9);
    --card-border: rgba(29, 154, 92, 0.16);
    --shadow-sm: 0 1px 2px rgba(10, 15, 13, 0.06);
    --shadow-md: 0 10px 28px rgba(10, 30, 20, 0.1);
    --focus-ring: 0 0 0 3px rgba(29, 154, 92, 0.35);
  }
}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;min-height:100dvh;background:var(--bg-gradient);color:var(--text);}
.open-wrap{min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:1.25rem;}
.open-card{
  width:100%;max-width:26rem;padding:1.75rem 1.5rem;border-radius:var(--radius-lg);
  background:var(--surface-glass);border:1px solid var(--card-border);
  box-shadow:var(--shadow-md);backdrop-filter:blur(12px);
}
.open-card--simple{text-align:left;}
.open-brand{display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem;}
.open-brand img{width:2.5rem;height:2.5rem;border-radius:50%;object-fit:cover;background:#000;box-shadow:0 0 0 1px var(--card-border);}
.open-brand span{font-family:var(--heading);font-weight:600;font-size:0.95rem;color:var(--text-h);}
.open-card h1{
  font-family:var(--heading);font-weight:600;font-size:1.35rem;letter-spacing:-0.02em;line-height:1.2;
  color:var(--text-h);margin:0 0 0.5rem;
}
.open-lead{margin:0 0 1.25rem;font-size:0.92rem;color:var(--muted);line-height:1.5;}
.open-body{margin:0 0 1rem;font-size:0.92rem;line-height:1.5;color:var(--text);}
.loader{
  display:flex;flex-direction:column;align-items:center;gap:0.65rem;margin:0 0 1.35rem;
  padding:1rem 0;border-top:1px solid var(--card-border);border-bottom:1px solid var(--card-border);
  transition:opacity 0.35s ease, visibility 0.35s ease;
}
.loader--hidden{opacity:0;visibility:hidden;height:0;margin:0;padding:0;overflow:hidden;border:none;}
.loader-text{margin:0;font-size:0.88rem;color:var(--muted);}
.spinner{
  width:2.25rem;height:2.25rem;border-radius:50%;
  border:3px solid var(--accent-soft);border-top-color:var(--accent);
  animation:sub-spin 0.75s linear infinite;
}
@keyframes sub-spin{to{transform:rotate(360deg)}}
.actions{display:flex;flex-direction:column;gap:0.6rem;}
@media (min-width:420px){.actions{flex-direction:row;flex-wrap:wrap;}}
.btn-primary{
  display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;
  flex:1;min-width:10rem;padding:0.6rem 1.1rem;border-radius:var(--radius-lg);border:none;
  font:inherit;font-weight:600;cursor:pointer;text-decoration:none;text-align:center;
  background:linear-gradient(135deg,var(--brand-mint) 0%,var(--brand-teal) 100%);
  color:var(--on-accent);box-shadow:var(--shadow-sm);
  transition:filter 0.2s ease, transform 0.15s ease, box-shadow 0.2s ease;
}
.btn-primary:hover{filter:brightness(1.06);box-shadow:var(--shadow-md);}
.btn-primary:focus-visible{outline:none;box-shadow:var(--focus-ring),var(--shadow-sm);}
.btn-secondary{
  display:inline-flex;align-items:center;justify-content:center;gap:0.35rem;
  flex:1;min-width:10rem;padding:0.55rem 1rem;border-radius:var(--radius-lg);
  border:1px solid var(--card-border);background:var(--surface-glass);
  color:var(--text-h);font:inherit;font-weight:600;cursor:pointer;text-decoration:none;text-align:center;
  transition:border-color 0.2s ease, background 0.2s ease;
}
.btn-secondary:hover{border-color:var(--accent-border);background:var(--accent-soft);}
.btn-secondary:focus-visible{outline:none;box-shadow:var(--focus-ring);}
@media (prefers-color-scheme: light){
  .btn-primary{background:linear-gradient(135deg,var(--accent) 0%,var(--accent-muted) 100%);}
}
.open-hint{margin:1.1rem 0 0;font-size:0.82rem;color:var(--muted);line-height:1.45;}
"""


def _open_app_page_head(title: str) -> str:
    t = html.escape(title)
    return (
        "<!DOCTYPE html><html lang=\"ru\"><head>"
        "<meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        "<meta name=\"theme-color\" content=\"#000000\" media=\"(prefers-color-scheme: dark)\"/>"
        "<meta name=\"theme-color\" content=\"#f2f7f4\" media=\"(prefers-color-scheme: light)\"/>"
        f"<title>{t}</title>"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\"/>"
        "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin/>"
        "<link href=\"https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700"
        "&family=Sora:wght@500;600;700&display=swap\" rel=\"stylesheet\"/>"
        "<link rel=\"icon\" href=\"/icons/favicon.svg\" type=\"image/svg+xml\"/>"
        f"<style>{_SUBSCRIPTION_OPEN_LANDING_CSS}</style>"
        "</head><body>"
    )


def _open_app_page(
    title: str,
    paragraph: str | None,
    deeplink: str | None,
    button_text: str,
    store_links: AppStoreLinks | None = None,
    client_display_name: str | None = None,
    store_platform: str | None = None,
) -> str:
    if not deeplink:
        chunks = [
            _open_app_page_head(title),
            "<div class=\"open-wrap\"><div class=\"open-card open-card--simple\">",
            "<div class=\"open-brand\"><img src=\"/icons/podorozhnik-logo.png\" alt=\"\" "
            "onerror=\"this.style.display='none'\"/><span>Подорожник VPN</span></div>",
            f"<h1>{html.escape(title)}</h1>",
        ]
        if paragraph:
            chunks.append(f"<p class=\"open-body\">{html.escape(paragraph)}</p>")
        chunks.append("</div></div></body></html>")
        return "".join(chunks)

    js_u = json.dumps(deeplink)
    sl = store_links or AppStoreLinks()
    has_store = sl.any()
    js_l = json.dumps(
        {
            "windows": sl.windows,
            "android": sl.android,
            "ios": sl.ios,
            "web": sl.web,
        }
        if has_store
        else None,
    )
    dl_name = (client_display_name or "клиент").strip()
    open_l = html.escape(button_text)
    dl_l = html.escape(f"Скачать {dl_name}")
    forced_js = "null" if not store_platform else json.dumps(store_platform)
    hint = (
        "Если приложение не открылось, нажмите «Открыть». "
        + (
            "«Скачать» — страница магазина или сайта для выбранной платформы (из адреса или по устройству)."
            if has_store
            else "Установите клиент вручную, если ещё не стоит."
        )
    )
    script = (
        "<script>(function(){"
        "var d=" + js_u + ",L=" + js_l + ";"
        "var FORCED_PLATFORM=" + forced_js + ";"
        "function storeHrefForPlatform(l,p){"
        "if(!l||!p)return null;"
        "if(p===\"android\")return l.android||null;"
        "if(p===\"ios\")return l.ios||null;"
        "if(p===\"windows\")return l.windows||l.web||null;"
        "return null;}"
        "function pick(l){"
        "if(!l)return null;"
        "if(FORCED_PLATFORM){"
        "var fh=storeHrefForPlatform(l,FORCED_PLATFORM);"
        "if(fh)return fh;}"
        "var u=navigator.userAgent||\"\";"
        "if(/android/i.test(u)&&l.android)return l.android;"
        "if((/iPhone|iPad|iPod/i.test(u))&&l.ios)return l.ios;"
        "if((/Win64|Windows NT|Win32|Windows Phone/i).test(u)){"
        "if(l.windows)return l.windows;if(l.web)return l.web;}"
        "if((/Macintosh|Mac OS X|Linux|X11/).test(u)&&!(/iPhone|iPad|iPod/i.test(u))){"
        "if(l.windows)return l.windows;if(l.web)return l.web;}"
        "if(l.windows)return l.windows;if(l.web)return l.web;if(l.android)return l.android;if(l.ios)return l.ios;"
        "return null;}"
        "var s=pick(L);"
        "var loader=document.getElementById(\"sub-loader\");"
        "var btnDl=document.getElementById(\"btn-dl\");"
        "function hideLoader(){if(loader)loader.classList.add(\"loader--hidden\");}"
        "function onLeave(){hideLoader();}"
        "if(btnDl){if(s){btnDl.href=s;}else{btnDl.style.display=\"none\";}}"
        "window.addEventListener(\"blur\",onLeave,{passive:true});"
        "document.addEventListener(\"visibilitychange\",function(){"
        "if(document.hidden)onLeave();},{passive:true});"
        "setTimeout(function(){if(document.visibilityState===\"visible\")hideLoader();},3400);"
        "try{location.replace(d);}catch(e){}"
        "})();</script>"
    )
    return (
        _open_app_page_head(title)
        + "<div class=\"open-wrap\"><div class=\"open-card\">"
        + "<div class=\"open-brand\"><img src=\"/icons/podorozhnik-logo.png\" alt=\"\" "
        "onerror=\"this.style.display='none'\"/><span>Подорожник VPN</span></div>"
        + f"<h1>{html.escape(title)}</h1>"
        + "<p class=\"open-lead\">Один раз пробуем открыть приложение, если оно уже установлено. "
        "Установка — только по кнопке «Скачать».</p>"
        + "<div class=\"loader\" id=\"sub-loader\" aria-live=\"polite\">"
        + "<div class=\"spinner\" role=\"status\" aria-label=\"Загрузка\"></div>"
        + "<p class=\"loader-text\">Подключаем…</p></div>"
        + "<div class=\"actions\">"
        + f"<a class=\"btn-primary\" id=\"btn-open\" href={js_u}>{open_l}</a>"
        + f"<a class=\"btn-secondary\" id=\"btn-dl\" href=\"#\">{dl_l}</a>"
        + "</div>"
        + f"<p class=\"open-hint\">{html.escape(hint)}</p>"
        + "</div></div>"
        + script
        + "</body></html>"
    )


@router.get(
    "/sub/{subscription_token}/open/{client}",
    summary=f"Открыть подписку в приложении (client: {_OPEN_APPS_DOC})",
    response_class=HTMLResponse,
)
async def subscription_open_in_app(
    request: Request,
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
    client: str = Path(
        ...,
        description=f"Идентификатор клиента. Доступно: {_OPEN_APPS_DOC}",
    ),
    platform: str | None = Query(
        None,
        description="Платформа для кнопки «Скачать»: windows | android | ios (иначе — по User-Agent).",
    ),
) -> HTMLResponse:
    app = get_subscription_open_app(client)
    if app is None:
        return RedirectResponse(
            url=_cabinet_redirect_url(extra_query={"unknown_client": "1"}),
            status_code=302,
        )

    user = table_select_one(session, User, filters={"token": subscription_token})
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
    return _client_landing_page(
        request,
        user,
        app,
        store_platform=_normalize_store_platform(platform),
    )


@router.get(
    "/sub/{subscription_token}",
    summary="Подписка: text/plain, одна строка Base64 (v2rayNG, Nekoray и др.)",
    response_class=Response,
)
async def subscription_base64_by_token(
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> Response:
    payload = await _subscription_payload_for_token(subscription_token, session)
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
    )


@router.get(
    "/sub/{subscription_token}/json",
    response_model=SubscriptionPayload,
    summary="Подписка (JSON): узлы, vless:// и поле subscription_base64",
)
async def subscription_json_by_token(
    session: ReadonlySessionDep,
    subscription_token: str = _SUBSCRIPTION_TOKEN_PATH,
) -> SubscriptionPayload:
    return await _subscription_payload_for_token(subscription_token, session)
