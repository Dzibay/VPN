"""Подписка /sub: выдача конфигов, учёт устройств, ежедневный sync Xray в очередь."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml
from urllib.parse import quote, urlencode

from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import URL as StarletteURL
from starlette.requests import Request

from app.config import Settings, settings
from app.domain.subscription import user_has_active_subscription
from app.domain.subscription_public_base import site_address_to_public_origin
from app.domain.subscription_userinfo import (
    build_subscription_userinfo_header_value,
    subscription_announce_header_value,
)
from app.domain.user_traffic import user_traffic_totals
from app.domain.subscription_open_apps import SUBSCRIPTION_IMPORT_DISPLAY_NAME
from app.domain.subscription_open_apps import AppStoreLinks, get_subscription_open_app
from app.domain.models.subscription import SubscriptionOpenPageData, SubscriptionPayload
from app.domain.services.users_service import ensure_sync_xray_clients_all_servers_enqueued
from app.infrastructure.database.operations import table_select_one
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription_service")

def subscription_servers_for_delivery(rows: list[Server]) -> list[Server]:
    """
    Узлы, которые попадают в тело подписки (JSON / Base64 / Clash).

    Если в выдаче есть пара каскада (РФ-вход с cascade_next_server_id), отдельная
    строка для внешнего exit не показывается — пользователь подключается только ко
    входу. Имя узла — как у одиночного сервера (без пометки «каскад»).
    Одиночные серверы и РФ-вход без привязанного exit не меняются.
    """
    referenced_exit_ids = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    if not referenced_exit_ids:
        return rows
    return [s for s in rows if s.id not in referenced_exit_ids]


def _subscription_server_rows(session: Session) -> list[Server]:
    """
    Все валидные узлы для ссылки в подписке (до фильтра каскада на выдаче).

    Дальше ``subscription_servers_for_delivery`` убирает внешние exit из пар
    «РФ-вход → exit», чтобы в клиенте не дублировать прямой доступ к exit.
    """
    stmt = (
        select(Server)
        .where(
            Server.is_active.is_(True),
            Server.provision_ready.is_(True),
            Server.reality_public_key.isnot(None),
            Server.reality_public_key != "",
        )
        .order_by(Server.load_percent.asc(), Server.id.asc())
    )
    return list(session.scalars(stmt).all())


def subscription_servers_from_db() -> list[Server]:
    """
    Узлы для выдачи в подписке: только чтение из БД (servers.load_percent обновляет фоновый планировщик).
    """
    db = SessionLocal()
    try:
        return _subscription_server_rows(db)
    finally:
        db.close()


def _primary_sni(server_names: str, dest: str) -> str:
    for part in (server_names or "").split(","):
        host = part.strip().split(":", 1)[0].strip()
        if host:
            return host
    d = (dest or "").strip()
    if not d:
        return ""
    return d.rsplit(":", 1)[0] if ":" in d else d


def _node_subscription_label(
    s: Server,
    *,
    exit_ids_referenced: set[int],
) -> str:
    """
    Имя для подписки (vless #fragment и JSON name): одиночные узлы и РФ-вход с exit
    без отдельной пометки; РФ-вход без exit — «(RU, прямой)»; для exit из пары
    «(прямой)» — только если узел ещё попал в выдачу (обычно exit скрыт).
    """
    base = (s.name or s.country or s.host or "node").strip()
    if s.is_cascade_ru_entry and s.cascade_next_server_id is None:
        return f"{base} (RU, прямой)"
    if s.id in exit_ids_referenced and not s.is_cascade_ru_entry:
        return f"{base} (прямой)"
    return base


def _vless_reality_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
) -> str | None:
    pbk = (s.reality_public_key or "").strip()
    if not pbk or "(" in pbk:
        log.warning(
            "Пропуск узла id=%s в подписке: некорректный reality_public_key",
            s.id,
        )
        return None
    sid = (s.reality_short_id or "").strip()
    if not sid:
        log.warning("Пропуск узла id=%s: пустой reality_short_id", s.id)
        return None
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (s.reality_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести SNI", s.id)
        return None

    params = {
        "encryption": "none",
        "security": "reality",
        "type": "tcp",
        "headerType": "none",
        "flow": flow,
        "sni": sni,
        "fp": fp,
        "pbk": pbk,
        "sid": sid,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _server_to_subscription_dict(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
) -> dict[str, Any]:
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    uid = (client_uuid or "").strip()
    display_name = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    return {
        "id": s.id,
        "name": display_name,
        "country": s.country,
        "address": s.host,
        "port": s.port,
        "uuid": uid,
        "flow": s.vless_flow,
        "encryption": "none",
        "network": "tcp",
        "security": "reality",
        "sni": sni,
        "fingerprint": s.reality_fingerprint,
        "public_key": s.reality_public_key,
        "short_id": s.reality_short_id,
        "dest": s.reality_dest,
        "server_names": s.reality_server_names,
    }


def _unique_clash_proxy_name(base_label: str, seen: dict[str, int]) -> str:
    b = (base_label or "").strip() or "node"
    if b not in seen:
        seen[b] = 0
        return b
    seen[b] += 1
    return f"{b} ({seen[b]})"


def build_clash_subscription_yaml(user: User, rows: list[Server]) -> str:
    """Clash Meta: VLESS + REALITY; то же множество узлов, что и в Base64-подписке."""
    rows = subscription_servers_for_delivery(rows)
    client_uuid = (user.vless_uuid or "").strip()
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}
    for s in rows:
        if (
            _vless_reality_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
            )
            is None
        ):
            continue
        label = _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
        name = _unique_clash_proxy_name(label, names_seen)
        pbk = (s.reality_public_key or "").strip()
        sid = (s.reality_short_id or "").strip()
        flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
        fp = (s.reality_fingerprint or "").strip() or "chrome"
        sni = _primary_sni(s.reality_server_names, s.reality_dest)
        host = (s.host or "").strip()
        proxies.append(
            {
                "name": name,
                "type": "vless",
                "server": host,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "tcp",
                "tls": True,
                "udp": True,
                "flow": flow,
                "servername": sni,
                "reality-opts": {
                    "public-key": pbk,
                    "short-id": sid,
                },
                "client-fingerprint": fp,
            }
        )
    group_name = SUBSCRIPTION_IMPORT_DISPLAY_NAME
    proxy_names = [p["name"] for p in proxies]
    if not proxy_names:
        doc: dict[str, Any] = {"proxies": [], "proxy-groups": [], "rules": []}
    else:
        doc = {
            "proxies": proxies,
            "proxy-groups": [
                {
                    "name": group_name,
                    "type": "select",
                    "proxies": proxy_names,
                }
            ],
            "rules": [f"MATCH,{group_name}"],
        }
    return yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def build_subscription_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    rows = subscription_servers_for_delivery(rows)
    client_uuid = (user.vless_uuid or "").strip()
    # id узлов, на которые RU-входа с каскадом ссылаются как на exit
    exit_ids_referenced: set[int] = {
        int(s.cascade_next_server_id)
        for s in rows
        if s.cascade_next_server_id is not None
    }
    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []
    for s in rows:
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
            )
        )
        uri = _vless_reality_share_uri(
            s,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
        )
        if uri:
            uris.append(uri)
    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )


SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE = (
    "Достигнуто максимальное количество подключений (устройств). "
    "Освободите слот в личном кабинете или обратитесь в поддержку."
)


def _norm_header(headers: Request.headers, key: str) -> str | None:
    raw = headers.get(key)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def subscription_device_fingerprint(request: Request) -> str:
    """
    Happ / v2raytun / FlClash передают x-hwid; без него — устойчивый ключ из типичных заголовков.
    """
    headers = request.headers
    hwid = _norm_header(headers, "x-hwid")
    if hwid:
        return f"hw:{hwid.strip().lower()}"
    ua = (_norm_header(headers, "user-agent") or "").encode("utf-8", errors="replace")
    dm = (_norm_header(headers, "x-device-model") or "").encode("utf-8", errors="replace")
    dos = (_norm_header(headers, "x-device-os") or "").encode("utf-8", errors="replace")
    vos = (_norm_header(headers, "x-ver-os") or "").encode("utf-8", errors="replace")
    h = hashlib.sha256(b"|".join((ua, dm, dos, vos))).hexdigest()
    return f"hdr:{h}"


def effective_subscription_device_limit(settings: Settings) -> int | None:
    """
    Положительное число — лимит разных устройств; None — без ограничения.

    Значение берётся из ``settings.subscription_max_devices`` (переменная окружения SUBSCRIPTION_MAX_DEVICES).
    Любое значение ≤ 0 означает «без лимита».
    """
    lim = int(settings.subscription_max_devices)
    if lim <= 0:
        return None
    return lim


def _device_row_fields(request: Request) -> dict:
    headers = request.headers
    now = datetime.now(timezone.utc)
    return {
        "user_agent": _norm_header(headers, "user-agent"),
        "os": _norm_header(headers, "x-device-os"),
        "hwid_raw": _norm_header(headers, "x-hwid"),
        "updated_at": now,
    }


def register_or_touch_subscription_device(
    session: Session,
    *,
    settings: Settings,
    user: User,
    request: Request,
) -> bool:
    """
    Сохраняет или обновляет запись устройства.

    Лимит уникальных устройств проверяется здесь всегда (включая истёкшую подписку), если в API
    задано положительное ``SUBSCRIPTION_MAX_DEVICES``. Новое устройство при исчерпанном лимите
    не регистрируется — возвращается ``False``; обработчик /sub отдаёт пустой список узлов и
    текст в заголовке ``announce``.

    :returns: ``True``, если клиенту можно выдавать узлы (известное устройство или успешная регистрация).
    """
    fingerprint = subscription_device_fingerprint(request)
    limit = effective_subscription_device_limit(settings)

    # Сериализуем по пользователю, чтобы два новых клиента параллельно не превысили лимит.
    session.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": int(user.id)})

    row = session.execute(
        select(SubscriptionDevice).where(
            SubscriptionDevice.user_id == user.id,
            SubscriptionDevice.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()

    fields = _device_row_fields(request)

    if row is None:
        if limit is not None:
            cnt = session.execute(
                select(func.count()).select_from(SubscriptionDevice).where(
                    SubscriptionDevice.user_id == user.id,
                )
            ).scalar_one()
            if int(cnt or 0) >= limit:
                return False
        now = datetime.now(timezone.utc)
        session.add(
            SubscriptionDevice(
                user_id=user.id,
                fingerprint=fingerprint,
                created_at=now,
                **fields,
            )
        )
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    return True


def list_subscription_connection_records(
    session: Session, user_id: int
) -> list[dict[str, int | str | None]]:
    rows = session.execute(
        select(
            SubscriptionDevice.id,
            SubscriptionDevice.os,
            SubscriptionDevice.user_agent,
        )
        .where(SubscriptionDevice.user_id == user_id)
        .order_by(SubscriptionDevice.updated_at.desc()),
    ).all()
    return [{"id": int(r[0]), "os": r[1], "user_agent": r[2]} for r in rows]


def count_subscription_devices_for_user(session: Session, user_id: int) -> int:
    n = session.execute(
        select(func.count())
        .select_from(SubscriptionDevice)
        .where(SubscriptionDevice.user_id == user_id),
    ).scalar_one()
    return int(n or 0)


_STORE_PLATFORM_KEYS_SUB = frozenset({"windows", "android", "ios", "macos", "linux"})


def normalize_subscription_store_platform(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    return v if v in _STORE_PLATFORM_KEYS_SUB else None


def subscription_cabinet_redirect_url(cfg: Settings | None = None, *, extra_query: dict[str, str] | None = None) -> str:
    cfg = cfg or settings
    raw = (cfg.public_cabinet_url or "").strip().rstrip("/")
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


def subscription_public_base_url(cfg: Settings | None = None) -> str:
    cfg = cfg or settings
    return site_address_to_public_origin(cfg.site_address)


def user_by_subscription_token(session: Session, subscription_token: str) -> User | None:
    return table_select_one(session, User, filters={"token": subscription_token})


def subscription_open_spa_url(
    subscription_token: str,
    client: str,
    *,
    platform: str | None,
    cfg: Settings | None = None,
) -> str:
    cfg = cfg or settings
    base = subscription_public_base_url(cfg)
    t = quote(subscription_token, safe="")
    c = quote(client, safe="")
    path = f"{base}/sub/{t}/open/{c}"
    norm = normalize_subscription_store_platform(platform)
    if norm:
        return f"{path}?{urlencode({'platform': norm})}"
    return path


def subscription_open_redirect_would_loop(request: Request, redirect_url: str) -> bool:
    try:
        target = StarletteURL(redirect_url)
        cur = request.url
    except Exception:
        return False
    return (
        target.scheme == cur.scheme
        and target.netloc == cur.netloc
        and target.path == cur.path
        and str(target.query) == str(cur.query)
    )


async def subscription_payload_rows_for_resolved_user(
    session: Session,
    user: User,
    *,
    device_allowed: bool = True,
) -> tuple[SubscriptionPayload, User, list[Server]]:
    if not user_has_active_subscription(user):
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=False,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    if not device_allowed:
        return (
            SubscriptionPayload(
                valid_until=user.subscription_until,
                subscription_active=True,
                servers=[],
                vless_uris=[],
                subscription_base64="",
            ),
            user,
            [],
        )

    rows = await run_in_threadpool(subscription_servers_from_db)
    return build_subscription_payload(user, rows), user, rows


def subscription_maybe_register_device(
    *,
    session: Session,
    request: Request,
    user: User | None,
    cfg: Settings | None = None,
) -> bool:
    cfg = cfg or settings
    if user is None:
        return True
    return register_or_touch_subscription_device(
        session,
        settings=cfg,
        user=user,
        request=request,
    )


def subscription_client_metadata_headers(
    session: Session,
    user: User,
    *,
    device_limit_rejected: bool = False,
) -> dict[str, str]:
    up_b, down_b, _ = user_traffic_totals(session, int(user.id))
    userinfo = build_subscription_userinfo_header_value(
        valid_until=user.subscription_until,
        upload=up_b,
        download=down_b,
        total=0,
    )
    active = user_has_active_subscription(user)
    if device_limit_rejected and active:
        announce_raw = SUBSCRIPTION_DEVICE_LIMIT_ANNOUNCE
    elif not active:
        announce_raw = "Подписка истекла — продлите подписку в личном кабинете или боте."
    else:
        announce_raw = ""
    return {
        "subscription-userinfo": userinfo,
        "profile-update-interval": "2",
        "profile-title": "Podorozhnik VPN",
        "support-url": "",
        "profile-web-page-url": "",
        "announce": subscription_announce_header_value(announce_raw),
        "announce-url": "",
    }


def subscription_build_open_page_data(
    user: User | None,
    app,
    *,
    store_platform: str | None,
) -> SubscriptionOpenPageData:
    forced = normalize_subscription_store_platform(store_platform)
    title = f"Подключение — {app.display_name}"
    headline = title
    open_label = f"Открыть в {app.display_name}"
    lead = (
        "Один раз пробуем открыть приложение, если оно уже установлено. "
        "Если приложение не установлено - нажмите кнопку Скачать или перейдите на сайт приложения"
    )
    hint = "Если приложение не открылось, но установлено - нажмите «Открыть». "

    if user is None:
        return SubscriptionOpenPageData(
            state="invalid_token",
            title="Ссылка недействительна",
            headline="Ссылка недействительна",
            message="Проверьте ссылку или получите новую в боте / личном кабинете.",
            deeplink=None,
            open_button_label="",
            lead=None,
            hint=None,
            store_links=None,
            forced_platform=forced,
        )

    base = subscription_public_base_url()
    suffix = (app.subscription_fetch_path_suffix or "").strip()
    subscription_url = f"{base}/sub/{user.token}{suffix}"
    deeplink = app.build_deeplink(subscription_url)
    sl: AppStoreLinks = app.store_links
    store_json = sl.to_public_json_dict() if sl.any() else None

    active = user_has_active_subscription(user)
    lead_active = lead
    lead_inactive = (
        "Подписка сейчас не активна — узлы VPN в клиенте появятся после продления. "
        "Приложение можно открыть и заранее добавить ссылку подписки — список серверов будет пустым, пока подписка не станет активной."
    )

    return SubscriptionOpenPageData(
        state="ok",
        title=title,
        headline=headline,
        message=None,
        deeplink=deeplink,
        open_button_label=open_label,
        lead=lead_active if active else lead_inactive,
        hint=hint,
        store_links=store_json,
        forced_platform=forced,
    )


def _seconds_until_next_local_time(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daily_xray_clients_sync_enqueue() -> None:
    """Поставить в очередь sync inbound (идемпотентно, см. coalesce по job_id в users_service)."""
    try:
        jid = ensure_sync_xray_clients_all_servers_enqueued()
        log.info("Ежедневный sync клиентов Xray на всех серверах: job_id=%s", jid)
    except RedisError:
        log.warning(
            "Ежедневный sync клиентов Xray: не удалось поставить в очередь (Redis)",
            exc_info=True,
        )


async def subscription_daily_xray_sync_loop() -> None:
    """Корутина lifespan API: раз в сутки в заданное локальное время."""
    if not settings.subscription_daily_xray_clients_sync_enabled:
        log.info("Планировщик ежедневного sync Xray выключен")
        return
    hour = int(settings.subscription_daily_xray_clients_sync_hour_local)
    minute = int(settings.subscription_daily_xray_clients_sync_minute_local)
    log.info(
        "Планировщик ежедневного sync Xray: локальное время %02d:%02d",
        hour,
        minute,
    )
    try:
        while True:
            delay = _seconds_until_next_local_time(hour, minute)
            log.debug(
                "Ежедневный sync Xray: сон %.0f с до следующего запуска",
                delay,
            )
            await asyncio.sleep(delay)
            try:
                await run_in_threadpool(run_daily_xray_clients_sync_enqueue)
            except Exception:
                log.exception("Ежедневный sync Xray: ошибка")
    except asyncio.CancelledError:
        log.info("Планировщик ежедневного sync Xray остановлен")
        raise
