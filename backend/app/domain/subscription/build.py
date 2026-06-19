"""Сборка тела подписки: Happ JSON (по UA) или Base64 share-ссылки, Clash YAML.

Happ (``happ`` в User-Agent): ``application/json`` — Auto, Auto (Белые списки), Auto (YouTube), узлы, tiered WL.

v2raytun / v2rayNG: ``text/plain`` Base64 — Auto, Auto (Белые списки), Auto (YouTube), затем все узлы.

Clash (``clash`` / ``hiddify`` в UA): YAML — отдельно в эндпоинте, здесь не собирается.

Узлы с ``is_hidden=true`` в подписку не попадают (только админка / метрики / провижининг).

Каскад: внешние exit узлы из пар «РФ-вход → exit» в список не попадают
(``subscription_servers_for_delivery``).

Параметр ``fp`` (uTLS) в ``vless://`` и поле ``fingerprint`` в JSON узла: при каждой
выдаче подписки случайно выбирается из chrome / firefox / safari / edge (не из БД).
"""

from __future__ import annotations

import copy
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import yaml
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BRAND_NAME
from app.domain.models.subscription import SubscriptionPayload
from app.domain.servers.reality_defaults import normalize_reality_spider_x
from app.domain.subscription.happ_subscription_encode import (
    encode_subscription_base64_lines,
    encode_subscription_json_array,
)
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.build")

SUBSCRIPTION_AUTO_RECOMMENDED_LABEL = "🔥 Auto (рекомендуемый)"
SUBSCRIPTION_AUTO_WHITELIST_LABEL = "📄 Auto (Белые списки)"
SUBSCRIPTION_AUTO_YOUTUBE_LABEL = "▶️ Auto (YouTube)"

_AUTO_BALANCER_PROBE_URL = "https://www.gstatic.com/generate_204"
_AUTO_YOUTUBE_BALANCER_PROBE_URL = "https://www.youtube.com/generate_204"

# uTLS fingerprint в vless:// и Clash: не из БД, а случайный на каждую выдачу подписки (DPI).
_SUBSCRIPTION_UTLS_FP_CHOICES: tuple[str, ...] = ("chrome", "firefox", "safari", "edge")


def _random_subscription_utls_fingerprint() -> str:
    return secrets.choice(_SUBSCRIPTION_UTLS_FP_CHOICES)


# Совпадает с install_xray_on_remote.sh (inbound sockopt); для сборки Xray JSON на клиенте.
_XRAY_VLESS_STREAM_SETTINGS_SOCKOPT: dict[str, Any] = {
    "sockopt": {
        "tcpFastOpen": True,
        "tcpcongestion": "bbr",
        "happyEyeballs": {
            "interleave": 1,
            "tryDelayMs": 250,
            "prioritizeIPv6": False,
            "maxConcurrentTry": 4,
        },
    }
}


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


async def subscription_servers_from_db(session: AsyncSession) -> list[Server]:
    """
    Узлы для выдачи в подписке: только чтение из БД (servers.load_percent обновляет фоновый планировщик).

    Скрытые узлы (``is_hidden``) и неактивные не включаются. Узлы с ``whitelist`` идут после всех
    остальных (внутри каждой группы — по нагрузке и id).

    Дальше ``subscription_servers_for_delivery`` убирает внешние exit из пар
    «РФ-вход → exit», чтобы в клиенте не дублировать прямой доступ к exit.
    """
    stmt = (
        select(Server)
        .where(
            Server.is_active.is_(True),
            Server.is_hidden.is_(False),
            Server.provision_ready.is_(True),
            or_(
                Server.proxy_kind == "hysteria2",
                Server.proxy_kind.in_(
                    ("vless_grpc", "vless_ws", "vless_xhttp", "vless_vk_cdn_xhttp")
                ),
                and_(
                    Server.proxy_kind == "vless",
                    Server.reality_public_key.isnot(None),
                    Server.reality_public_key != "",
                ),
            ),
        )
        .order_by(Server.whitelist.asc(), Server.load_percent.asc(), Server.id.asc())
    )
    return list((await session.scalars(stmt)).all())


def _primary_sni(server_names: str, dest: str) -> str:
    for part in (server_names or "").split(","):
        host = part.strip().split(":", 1)[0].strip()
        if host:
            return host
    d = (dest or "").strip()
    if not d:
        return ""
    return d.rsplit(":", 1)[0] if ":" in d else d


def _tls_sni_for_server(s: Server) -> str:
    return ((s.tls_sni or s.host or "").strip().rstrip("."))


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
    client_fingerprint: str,
    fragment_override: str | None = None,
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
    fp = (client_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести SNI", s.id)
        return None

    spx = normalize_reality_spider_x(s.reality_spider_x)
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
        "spx": spx,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _vless_grpc_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    fragment_override: str | None = None,
) -> str | None:
    service_name = (s.grpc_service_name or "grpc").strip()
    if not service_name:
        log.warning("Пропуск узла id=%s: пустой grpc_service_name", s.id)
        return None
    sni = _tls_sni_for_server(s)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести TLS SNI", s.id)
        return None
    params = {
        "encryption": "none",
        "security": "tls",
        "type": "grpc",
        "serviceName": service_name,
        "sni": sni,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _vless_ws_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    fragment_override: str | None = None,
) -> str | None:
    sni = _tls_sni_for_server(s)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести TLS SNI", s.id)
        return None
    wpath = (s.ws_path or "/vless").strip() or "/vless"
    if not wpath.startswith("/"):
        wpath = "/" + wpath
    params = {
        "encryption": "none",
        "security": "tls",
        "type": "ws",
        "path": wpath,
        "sni": sni,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _xhttp_extra(path: str) -> dict[str, Any]:
    return {
        "mode": "packet-up",
        "path": path,
    }


def _xhttp_vkcdn_extra(path: str) -> dict[str, Any]:
    return {
        "mode": "packet-up",
        "path": path,
        "xPaddingKey": "_dc",
        "xPaddingHeader": "X-Cache",
        "xPaddingMethod": "tokenish",
        "uplinkHTTPMethod": "GET",
        "xPaddingObfsMode": True,
        "xPaddingPlacement": "queryInHeader",
    }


def _xhttp_path_for_server(s: Server) -> str:
    kind = (s.proxy_kind or "vless").strip().lower()
    default = "/xhttp/" if kind == "vless_xhttp" else "/uploadfiles/"
    path = (s.xhttp_path or default).strip() or default
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def _vless_xhttp_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    fragment_override: str | None = None,
) -> str | None:
    host = (s.host or "").strip()
    sni = _tls_sni_for_server(s)
    if not host or not sni:
        log.warning("Пропуск узла id=%s: пустой host/SNI для XHTTP", s.id)
        return None
    path = _xhttp_path_for_server(s)
    params = {
        "encryption": "none",
        "security": "tls",
        "type": "xhttp",
        "host": sni,
        "path": path,
        "mode": "packet-up",
        "sni": sni,
        "fp": "chrome",
        "alpn": "h3,h2,http/1.1",
        "extra": json.dumps(_xhttp_extra(path), separators=(",", ":"), ensure_ascii=False),
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    if not uuid:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _vless_vkcdn_xhttp_share_uri(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    fragment_override: str | None = None,
) -> str | None:
    cdn = (s.cdn_domain or "").strip().rstrip(".")
    if not cdn:
        log.warning("Пропуск узла id=%s: пустой cdn_domain для VK CDN XHTTP", s.id)
        return None
    path = _xhttp_path_for_server(s)
    params = {
        "encryption": "none",
        "security": "tls",
        "type": "xhttp",
        "host": cdn,
        "path": path,
        "mode": "packet-up",
        "sni": cdn,
        "fp": "chrome",
        "alpn": "h3,h2,http/1.1",
        "extra": json.dumps(_xhttp_vkcdn_extra(path), separators=(",", ":"), ensure_ascii=False),
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    uuid = (client_uuid or "").strip()
    if not uuid:
        return None
    return f"vless://{uuid}@{cdn}:{int(s.port)}?{query}#{fragment}"


def _hysteria2_password_for_server(s: Server) -> str:
    return ((s.vless_uuid or "").replace("-", "")[:32] or f"hysteria{int(s.id)}")


def _hysteria2_share_uri(
    s: Server,
    *,
    exit_ids_referenced: set[int],
    fragment_override: str | None = None,
) -> str | None:
    host = (s.host or "").strip()
    if not host:
        return None
    pwd = quote(_hysteria2_password_for_server(s), safe="")
    sni = host
    params = {
        "sni": sni,
        "insecure": "1",
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (
        fragment_override
        if fragment_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    fragment = quote(remark, safe="")
    return f"hysteria2://{pwd}@{host}:{int(s.port)}?{query}#{fragment}"


def _server_to_subscription_dict(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    client_fingerprint: str,
    name_override: str | None = None,
) -> dict[str, Any]:
    kind = (s.proxy_kind or "vless").strip().lower()
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    display_name = (
        name_override
        if name_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
    if kind == "hysteria2":
        host = (s.host or "").strip()
        return {
            "id": s.id,
            "name": display_name,
            "country": s.country,
            "address": host,
            "port": s.port,
            "protocol": "hysteria2",
            "password": _hysteria2_password_for_server(s),
            "sni": host,
            "insecure": True,
            "network": "udp",
        }
    if kind == "vless_grpc":
        host = (s.host or "").strip()
        sni = _tls_sni_for_server(s)
        return {
            "id": s.id,
            "name": display_name,
            "country": s.country,
            "protocol": "vless",
            "address": host,
            "port": s.port,
            "uuid": (client_uuid or "").strip(),
            "encryption": "none",
            "network": "grpc",
            "security": "tls",
            "sni": sni,
            "serviceName": (s.grpc_service_name or "grpc").strip(),
        }
    if kind == "vless_ws":
        host = (s.host or "").strip()
        sni = _tls_sni_for_server(s)
        wpath = (s.ws_path or "/vless").strip() or "/vless"
        if not wpath.startswith("/"):
            wpath = "/" + wpath
        return {
            "id": s.id,
            "name": display_name,
            "country": s.country,
            "protocol": "vless",
            "address": host,
            "port": s.port,
            "uuid": (client_uuid or "").strip(),
            "encryption": "none",
            "network": "ws",
            "security": "tls",
            "sni": sni,
            "path": wpath,
        }
    if kind == "vless_xhttp":
        host = (s.host or "").strip()
        sni = _tls_sni_for_server(s)
        path = _xhttp_path_for_server(s)
        return {
            "id": s.id,
            "name": display_name,
            "country": s.country,
            "protocol": "vless",
            "address": host,
            "port": s.port,
            "uuid": (client_uuid or "").strip(),
            "encryption": "none",
            "network": "xhttp",
            "security": "tls",
            "sni": sni,
            "host": sni,
            "path": path,
            "mode": "packet-up",
            "alpn": ["h3", "h2", "http/1.1"],
            "fingerprint": "chrome",
            "xhttp_extra": _xhttp_extra(path),
        }
    if kind == "vless_vk_cdn_xhttp":
        cdn = (s.cdn_domain or "").strip().rstrip(".")
        path = _xhttp_path_for_server(s)
        return {
            "id": s.id,
            "name": display_name,
            "country": s.country,
            "protocol": "vless",
            "address": cdn,
            "port": s.port,
            "uuid": (client_uuid or "").strip(),
            "encryption": "none",
            "network": "xhttp",
            "security": "tls",
            "sni": cdn,
            "host": cdn,
            "path": path,
            "mode": "packet-up",
            "alpn": ["h3", "h2", "http/1.1"],
            "fingerprint": "chrome",
            "xhttp_extra": _xhttp_vkcdn_extra(path),
            "origin_domain": (s.origin_domain or "").strip().rstrip("."),
        }
    uid = (client_uuid or "").strip()
    return {
        "id": s.id,
        "name": display_name,
        "country": s.country,
        "protocol": "vless",
        "address": s.host,
        "port": s.port,
        "uuid": uid,
        "flow": s.vless_flow,
        "encryption": "none",
        "network": "tcp",
        "security": "reality",
        "sni": sni,
        "fingerprint": (client_fingerprint or "").strip() or "chrome",
        "public_key": s.reality_public_key,
        "short_id": s.reality_short_id,
        "dest": s.reality_dest,
        "server_names": s.reality_server_names,
        "reality_spider_x": normalize_reality_spider_x(s.reality_spider_x),
        "stream_settings": dict(_XRAY_VLESS_STREAM_SETTINGS_SOCKOPT),
    }


def _cascade_exit_ids_referenced(delivery_rows: list[Server]) -> set[int]:
    return {
        int(s.cascade_next_server_id)
        for s in delivery_rows
        if s.cascade_next_server_id is not None
    }


@dataclass(frozen=True)
class _SubscriptionDeliveryContext:
    """Единый контекст после фильтрации каскада: строки выдачи и id внешних exit."""

    delivery_rows: list[Server]
    exit_ids_referenced: set[int]


def _subscription_delivery_context(rows: list[Server]) -> _SubscriptionDeliveryContext:
    delivery = subscription_servers_for_delivery(rows)
    return _SubscriptionDeliveryContext(
        delivery_rows=delivery,
        exit_ids_referenced=_cascade_exit_ids_referenced(delivery),
    )


def _subscription_uri_and_fingerprint_by_server_id(
    ctx: _SubscriptionDeliveryContext,
    *,
    client_uuid: str,
) -> tuple[dict[int, str | None], dict[int, str]]:
    """Стандартный URI на узел и uTLS fp для подписки (один fp на server_id на выдачу)."""
    uri_by_id: dict[int, str | None] = {}
    fp_by_id: dict[int, str] = {}
    for s in ctx.delivery_rows:
        fp = _random_subscription_utls_fingerprint()
        fp_by_id[s.id] = fp
        kind = (s.proxy_kind or "vless").strip().lower()
        if kind == "hysteria2":
            uri_by_id[s.id] = _hysteria2_share_uri(
                s,
                exit_ids_referenced=ctx.exit_ids_referenced,
            )
        elif kind == "vless_grpc":
            uri_by_id[s.id] = _vless_grpc_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
            )
        elif kind == "vless_ws":
            uri_by_id[s.id] = _vless_ws_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
            )
        elif kind == "vless_xhttp":
            uri_by_id[s.id] = _vless_xhttp_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
            )
        elif kind == "vless_vk_cdn_xhttp":
            uri_by_id[s.id] = _vless_vkcdn_xhttp_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
            )
        else:
            uri_by_id[s.id] = _vless_reality_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                client_fingerprint=fp,
            )
    return uri_by_id, fp_by_id


def _is_vless_server(s: Server) -> bool:
    return (s.proxy_kind or "vless").strip().lower() in (
        "vless",
        "vless_grpc",
        "vless_ws",
        "vless_xhttp",
        "vless_vk_cdn_xhttp",
    )


def _pool_auto_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
    *,
    whitelist: bool | None = None,
) -> list[Server]:
    """
    VLESS с ``include_in_auto`` и валидным URI (группы Auto).

    ``whitelist=None`` — все auto; ``False`` — без WL; ``True`` — только WL.
    """
    out: list[Server] = []
    for s in ctx.delivery_rows:
        if not _is_vless_server(s) or not s.include_in_auto:
            continue
        if uri_by_id.get(s.id) is None:
            continue
        if whitelist is False and s.whitelist:
            continue
        if whitelist is True and not s.whitelist:
            continue
        out.append(s)
    return out


def _pool_auto_youtube_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> list[Server]:
    """
    VLESS для Auto (YouTube): ``include_in_auto``, ``google_routing_mode=entry``
    (YouTube через вход, не Gemini/exit) и валидный URI.
    """
    out: list[Server] = []
    for s in ctx.delivery_rows:
        if not _is_vless_server(s) or not s.include_in_auto:
            continue
        if (s.google_routing_mode or "exit").strip().lower() != "entry":
            continue
        if uri_by_id.get(s.id) is None:
            continue
        out.append(s)
    return out


def _pool_tiered_wl_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> list[Server]:
    """VLESS с ``whitelist`` и валидным URI — отдельный tiered-профиль (rec + WL, cost)."""
    out: list[Server] = []
    for s in ctx.delivery_rows:
        if not _is_vless_server(s) or not s.whitelist:
            continue
        if uri_by_id.get(s.id) is None:
            continue
        out.append(s)
    return out


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _auto_best_share_uri(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    exit_ids_referenced: set[int],
) -> str | None:
    """Один ``vless://`` на лучший узел пула (для Auto в Base64-подписке)."""
    best = _best_server_by_load(pool)
    if best is None:
        return None
    kind = (best.proxy_kind or "vless").strip().lower()
    if kind == "vless_grpc":
        return _vless_grpc_share_uri(
            best,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            fragment_override=remark,
        )
    if kind == "vless_ws":
        return _vless_ws_share_uri(
            best,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            fragment_override=remark,
        )
    if kind == "vless_xhttp":
        return _vless_xhttp_share_uri(
            best,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            fragment_override=remark,
        )
    if kind == "vless_vk_cdn_xhttp":
        return _vless_vkcdn_xhttp_share_uri(
            best,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            fragment_override=remark,
        )
    return _vless_reality_share_uri(
        best,
        client_uuid=client_uuid,
        exit_ids_referenced=exit_ids_referenced,
        client_fingerprint=fp_by_id[best.id],
        fragment_override=remark,
    )


def _append_clash_proxy(
    proxies: list[dict[str, Any]],
    s: Server,
    *,
    client_uuid: str,
    clash_name: str,
    client_fingerprint: str,
) -> None:
    kind = (s.proxy_kind or "vless").strip().lower()
    host = (s.host or "").strip()
    if kind == "hysteria2":
        proxies.append(
            {
                "name": clash_name,
                "type": "hysteria2",
                "server": host,
                "port": int(s.port),
                "password": _hysteria2_password_for_server(s),
                "sni": host,
                "skip-cert-verify": True,
                "udp": True,
            }
        )
        return
    if kind == "vless_grpc":
        sni = _tls_sni_for_server(s)
        service_name = (s.grpc_service_name or "grpc").strip()
        proxies.append(
            {
                "name": clash_name,
                "type": "vless",
                "server": host,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "grpc",
                "tls": True,
                "udp": True,
                "servername": sni,
                "grpc-opts": {"grpc-service-name": service_name},
            }
        )
        return
    if kind == "vless_ws":
        sni = _tls_sni_for_server(s)
        wpath = (s.ws_path or "/vless").strip() or "/vless"
        if not wpath.startswith("/"):
            wpath = "/" + wpath
        proxies.append(
            {
                "name": clash_name,
                "type": "vless",
                "server": host,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "ws",
                "tls": True,
                "udp": True,
                "servername": sni,
                "ws-opts": {"path": wpath},
            }
        )
        return
    if kind == "vless_xhttp":
        sni = _tls_sni_for_server(s)
        path = _xhttp_path_for_server(s)
        proxies.append(
            {
                "name": clash_name,
                "type": "vless",
                "server": host,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "xhttp",
                "tls": True,
                "udp": True,
                "servername": sni,
                "client-fingerprint": "chrome",
                "alpn": ["h3", "h2", "http/1.1"],
                "xhttp-opts": {
                    "path": path,
                    "host": sni,
                    "mode": "packet-up",
                    "extra": _xhttp_extra(path),
                },
            }
        )
        return
    if kind == "vless_vk_cdn_xhttp":
        cdn = (s.cdn_domain or "").strip().rstrip(".")
        path = _xhttp_path_for_server(s)
        proxies.append(
            {
                "name": clash_name,
                "type": "vless",
                "server": cdn,
                "port": int(s.port),
                "uuid": client_uuid,
                "network": "xhttp",
                "tls": True,
                "udp": True,
                "servername": cdn,
                "client-fingerprint": "chrome",
                "alpn": ["h3", "h2", "http/1.1"],
                "xhttp-opts": {
                    "path": path,
                    "host": cdn,
                    "mode": "packet-up",
                    "extra": _xhttp_vkcdn_extra(path),
                },
            }
        )
        return
    pbk = (s.reality_public_key or "").strip()
    sid = (s.reality_short_id or "").strip()
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (client_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    spx = normalize_reality_spider_x(s.reality_spider_x)
    proxies.append(
        {
            "name": clash_name,
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
                "spider-x": spx,
            },
            "client-fingerprint": fp,
            "tfo": True,
        }
    )


def _unique_clash_proxy_name(base_label: str, seen: dict[str, int]) -> str:
    b = (base_label or "").strip() or "node"
    if b not in seen:
        seen[b] = 0
        return b
    seen[b] += 1
    return f"{b} ({seen[b]})"


@dataclass(frozen=True)
class SubscriptionBuildContext:
    """Общий контекст для Happ JSON и Base64 (после фильтра каскада)."""

    delivery: _SubscriptionDeliveryContext
    client_uuid: str
    uri_by_id: dict[int, str | None]
    fp_by_id: dict[int, str]
    pool_rec: list[Server]
    pool_wl: list[Server]
    pool_youtube: list[Server]
    pool_wl_tiered: list[Server]

    @property
    def pool_auto(self) -> list[Server]:
        return [*self.pool_rec, *self.pool_wl]


def _subscription_build_context(user: User, rows: list[Server]) -> SubscriptionBuildContext:
    delivery = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        delivery, client_uuid=client_uuid
    )
    return SubscriptionBuildContext(
        delivery=delivery,
        client_uuid=client_uuid,
        uri_by_id=uri_by_id,
        fp_by_id=fp_by_id,
        pool_rec=_pool_auto_vless(delivery, uri_by_id, whitelist=False),
        pool_wl=_pool_auto_vless(delivery, uri_by_id, whitelist=True),
        pool_youtube=_pool_auto_youtube_vless(delivery, uri_by_id),
        pool_wl_tiered=_pool_tiered_wl_vless(delivery, uri_by_id),
    )


def build_clash_subscription_yaml(user: User, rows: list[Server]) -> str:
    """Clash Meta: VLESS+REALITY и/или Hysteria2; порядок как в Base64-подписке."""
    bctx = _subscription_build_context(user, rows)
    ctx = bctx.delivery

    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}
    name_by_server_id: dict[int, str] = {}

    for s in ctx.delivery_rows:
        if bctx.uri_by_id.get(s.id) is None:
            continue
        label = _node_subscription_label(s, exit_ids_referenced=ctx.exit_ids_referenced)
        name = _unique_clash_proxy_name(label, names_seen)
        name_by_server_id[s.id] = name
        _append_clash_proxy(
            proxies,
            s,
            client_uuid=bctx.client_uuid,
            clash_name=name,
            client_fingerprint=bctx.fp_by_id[s.id],
        )

    proxy_groups: list[dict[str, Any]] = []
    select_proxies: list[str] = []

    def _append_url_test_group(
        label: str,
        pool: list[Server],
        *,
        probe_url: str = _AUTO_BALANCER_PROBE_URL,
    ) -> None:
        member_names = [name_by_server_id[s.id] for s in pool if s.id in name_by_server_id]
        if not member_names:
            return
        group_name = _unique_clash_proxy_name(label, names_seen)
        proxy_groups.append(
            {
                "name": group_name,
                "type": "url-test",
                "proxies": member_names,
                "url": probe_url,
                "interval": 300,
                "tolerance": 50,
            }
        )
        select_proxies.append(group_name)

    _append_url_test_group(SUBSCRIPTION_AUTO_RECOMMENDED_LABEL, bctx.pool_rec)
    _append_url_test_group(SUBSCRIPTION_AUTO_WHITELIST_LABEL, bctx.pool_wl)
    _append_url_test_group(
        SUBSCRIPTION_AUTO_YOUTUBE_LABEL,
        bctx.pool_youtube,
        probe_url=_AUTO_YOUTUBE_BALANCER_PROBE_URL,
    )

    select_proxies.extend(p["name"] for p in proxies)

    group_name = BRAND_NAME
    if not select_proxies:
        doc: dict[str, Any] = {"proxies": [], "proxy-groups": [], "rules": []}
    else:
        proxy_groups.append(
            {
                "name": group_name,
                "type": "select",
                "proxies": select_proxies,
            }
        )
        doc = {
            "proxies": proxies,
            "proxy-groups": proxy_groups,
            "rules": [f"MATCH,{group_name}"],
        }
    return yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _servers_metadata(bctx: SubscriptionBuildContext) -> list[dict[str, Any]]:
    ctx = bctx.delivery
    return [
        _server_to_subscription_dict(
            s,
            client_uuid=bctx.client_uuid,
            exit_ids_referenced=ctx.exit_ids_referenced,
            client_fingerprint=bctx.fp_by_id[s.id],
        )
        for s in ctx.delivery_rows
    ]


def _happ_json_profiles(bctx: SubscriptionBuildContext) -> list[dict[str, Any]]:
    from app.domain.subscription.happ_competitor_json import (
        YOUTUBE_PROBE_URL,
        build_happ_auto_group_balanced_profile,
        build_happ_plain_server_profile,
        build_happ_tiered_wl_balanced_profile,
    )

    ctx = bctx.delivery
    profiles: list[dict[str, Any]] = []

    auto_doc = build_happ_auto_group_balanced_profile(
        SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        bctx.pool_auto,
        client_uuid=bctx.client_uuid,
        fp_by_id=bctx.fp_by_id,
        balancer_tag="auto-rec-balance",
    )
    if auto_doc:
        profiles.append(auto_doc)
        if bctx.pool_wl:
            wl_auto = copy.deepcopy(auto_doc)
            wl_auto["remarks"] = SUBSCRIPTION_AUTO_WHITELIST_LABEL
            profiles.append(wl_auto)

    youtube_doc = build_happ_auto_group_balanced_profile(
        SUBSCRIPTION_AUTO_YOUTUBE_LABEL,
        bctx.pool_youtube,
        client_uuid=bctx.client_uuid,
        fp_by_id=bctx.fp_by_id,
        balancer_tag="auto-youtube-balance",
        probe_url=YOUTUBE_PROBE_URL,
    )
    if youtube_doc:
        profiles.append(youtube_doc)

    pool_wl_tiered_ids = {wl.id for wl in bctx.pool_wl_tiered}
    for s in ctx.delivery_rows:
        if s.id in pool_wl_tiered_ids:
            continue
        doc = build_happ_plain_server_profile(
            _node_subscription_label(s, exit_ids_referenced=ctx.exit_ids_referenced),
            s,
            client_uuid=bctx.client_uuid,
            client_fingerprint=bctx.fp_by_id[s.id],
        )
        if doc:
            profiles.append(doc)

    for wl in bctx.pool_wl_tiered:
        tiered = build_happ_tiered_wl_balanced_profile(
            _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced),
            bctx.pool_rec,
            wl,
            client_uuid=bctx.client_uuid,
            fp_by_id=bctx.fp_by_id,
            balancer_tag=f"wl-{int(wl.id)}-balance",
        )
        if tiered:
            profiles.append(tiered)

    return profiles


def _base64_share_lines(bctx: SubscriptionBuildContext) -> list[str]:
    ctx = bctx.delivery
    lines: list[str] = []

    auto_rec = _auto_best_share_uri(
        SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        bctx.pool_rec,
        client_uuid=bctx.client_uuid,
        fp_by_id=bctx.fp_by_id,
        exit_ids_referenced=ctx.exit_ids_referenced,
    )
    if auto_rec:
        lines.append(auto_rec)

    if bctx.pool_wl:
        auto_wl = _auto_best_share_uri(
            SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            bctx.pool_wl,
            client_uuid=bctx.client_uuid,
            fp_by_id=bctx.fp_by_id,
            exit_ids_referenced=ctx.exit_ids_referenced,
        )
        if auto_wl:
            lines.append(auto_wl)

    auto_youtube = _auto_best_share_uri(
        SUBSCRIPTION_AUTO_YOUTUBE_LABEL,
        bctx.pool_youtube,
        client_uuid=bctx.client_uuid,
        fp_by_id=bctx.fp_by_id,
        exit_ids_referenced=ctx.exit_ids_referenced,
    )
    if auto_youtube:
        lines.append(auto_youtube)

    for s in ctx.delivery_rows:
        uri = bctx.uri_by_id.get(s.id)
        if uri:
            lines.append(uri)

    return lines


def _subscription_payload(
    user: User,
    bctx: SubscriptionBuildContext,
    *,
    happ_json: bool,
) -> SubscriptionPayload:
    if happ_json:
        profiles = _happ_json_profiles(bctx)
        body, media_type = encode_subscription_json_array(profiles)
        vless_uris = [p.get("remarks", "json") for p in profiles if p.get("remarks")]
    else:
        vless_uris = _base64_share_lines(bctx)
        body, media_type = encode_subscription_base64_lines(vless_uris)

    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=_servers_metadata(bctx),
        vless_uris=vless_uris,
        subscription_base64=body,
        subscription_media_type=media_type,
    )


def build_subscription_payload(
    user: User,
    rows: list[Server],
    *,
    happ_json: bool = False,
) -> SubscriptionPayload:
    bctx = _subscription_build_context(user, rows)
    return _subscription_payload(user, bctx, happ_json=happ_json)
