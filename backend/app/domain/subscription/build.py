"""Сборка тела подписки: Happ Base64 (JSON + share-ссылки), Clash Meta YAML.

Порядок Happ (``text/plain`` Base64, построчно):

1. JSON Auto (рекомендуемый), 2. JSON Auto (белые списки, дубликат),
3. ``vless://`` / ``hysteria2://`` обычных узлов, 4. JSON tiered WL.

Clash: ``url-test`` по пулу Auto, затем все узлы.

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
from app.domain.subscription.happ_subscription_encode import encode_happ_subscription_body
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.build")

SUBSCRIPTION_AUTO_RECOMMENDED_LABEL = "🔥 Auto (рекомендуемый)"
SUBSCRIPTION_AUTO_WHITELIST_LABEL = "📄 Auto (Белые списки)"

_AUTO_BALANCER_PROBE_URL = "https://www.gstatic.com/generate_204"

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
        else:
            uri_by_id[s.id] = _vless_reality_share_uri(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                client_fingerprint=fp,
            )
    return uri_by_id, fp_by_id


def _is_vless_server(s: Server) -> bool:
    return (s.proxy_kind or "vless").strip().lower() == "vless"


def _pool_auto_all_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> list[Server]:
    """Все VLESS с ``include_in_auto`` и валидным share-URI (для Auto-групп)."""
    return [
        s
        for s in ctx.delivery_rows
        if _is_vless_server(s)
        and bool(s.include_in_auto)
        and uri_by_id.get(s.id) is not None
    ]


def _pool_rec_auto_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> list[Server]:
    """VLESS без ``whitelist`` с ``include_in_auto`` (основной пул для tiered WL)."""
    return [
        s
        for s in ctx.delivery_rows
        if _is_vless_server(s)
        and bool(s.include_in_auto)
        and not s.whitelist
        and uri_by_id.get(s.id) is not None
    ]


def _pool_wl_auto_vless(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> list[Server]:
    """VLESS с ``whitelist`` и ``include_in_auto``."""
    return [
        s
        for s in ctx.delivery_rows
        if _is_vless_server(s)
        and bool(s.include_in_auto)
        and bool(s.whitelist)
        and uri_by_id.get(s.id) is not None
    ]


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


def build_clash_subscription_yaml(user: User, rows: list[Server]) -> str:
    """Clash Meta: VLESS+REALITY и/или Hysteria2; порядок как в Base64-подписке."""
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_auto = _pool_auto_all_vless(ctx, uri_by_id)

    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}
    name_by_server_id: dict[int, str] = {}

    for s in ctx.delivery_rows:
        if uri_by_id.get(s.id) is None:
            continue
        label = _node_subscription_label(s, exit_ids_referenced=ctx.exit_ids_referenced)
        name = _unique_clash_proxy_name(label, names_seen)
        name_by_server_id[s.id] = name
        _append_clash_proxy(
            proxies,
            s,
            client_uuid=client_uuid,
            clash_name=name,
            client_fingerprint=fp_by_id[s.id],
        )

    proxy_groups: list[dict[str, Any]] = []
    select_proxies: list[str] = []

    def _append_url_test_group(label: str, pool: list[Server]) -> None:
        member_names = [name_by_server_id[s.id] for s in pool if s.id in name_by_server_id]
        if not member_names:
            return
        group_name = _unique_clash_proxy_name(label, names_seen)
        proxy_groups.append(
            {
                "name": group_name,
                "type": "url-test",
                "proxies": member_names,
                "url": _AUTO_BALANCER_PROBE_URL,
                "interval": 300,
                "tolerance": 50,
            }
        )
        select_proxies.append(group_name)

    _append_url_test_group(SUBSCRIPTION_AUTO_RECOMMENDED_LABEL, pool_auto)
    if pool_auto:
        _append_url_test_group(SUBSCRIPTION_AUTO_WHITELIST_LABEL, pool_auto)

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


def build_subscription_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """Happ: JSON Auto-группы + share-ссылки обычных узлов + tiered WL."""
    from app.domain.subscription.happ_competitor_json import (
        build_happ_auto_group_balanced_profile,
        build_happ_tiered_wl_balanced_profile,
    )

    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_auto = _pool_auto_all_vless(ctx, uri_by_id)
    pool_rec = _pool_rec_auto_vless(ctx, uri_by_id)
    pool_wl = _pool_wl_auto_vless(ctx, uri_by_id)

    share_lines: list[str] = []
    tiered_profiles: list[dict[str, Any]] = []
    wl_dup: dict[str, Any] | None = None

    auto_doc = build_happ_auto_group_balanced_profile(
        SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        pool_auto,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        balancer_tag="auto-rec-balance",
    )
    if auto_doc:
        wl_dup = copy.deepcopy(auto_doc)
        wl_dup["remarks"] = SUBSCRIPTION_AUTO_WHITELIST_LABEL

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        uri = uri_by_id.get(s.id)
        if uri:
            share_lines.append(uri)

    for wl in pool_wl:
        remark = _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced)
        tiered = build_happ_tiered_wl_balanced_profile(
            remark,
            pool_rec,
            wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            balancer_tag=f"wl-{int(wl.id)}-balance",
        )
        if tiered:
            tiered_profiles.append(tiered)

    ordered_lines: list[str] = []
    if auto_doc:
        ordered_lines.append(
            json.dumps(auto_doc, ensure_ascii=False, separators=(",", ":"))
        )
    if wl_dup:
        ordered_lines.append(
            json.dumps(wl_dup, ensure_ascii=False, separators=(",", ":"))
        )
    ordered_lines.extend(share_lines)
    for tiered in tiered_profiles:
        ordered_lines.append(
            json.dumps(tiered, ensure_ascii=False, separators=(",", ":"))
        )

    body, media_type = encode_happ_subscription_body(
        fmt="lines",
        ordered_lines=ordered_lines,
    )

    servers_out: list[dict[str, Any]] = []
    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                client_fingerprint=fp_by_id[s.id],
            )
        )

    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=[
            *([auto_doc["remarks"]] if auto_doc and auto_doc.get("remarks") else []),
            *([wl_dup["remarks"]] if wl_dup and wl_dup.get("remarks") else []),
            *share_lines,
            *(
                p.get("remarks", "json")
                for p in tiered_profiles
                if p.get("remarks")
            ),
        ],
        subscription_base64=body,
        subscription_media_type=media_type,
    )
