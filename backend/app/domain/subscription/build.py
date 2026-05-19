"""Сборка тела подписки: список узлов, ``vless://`` URI, Base64, Clash Meta YAML.

Порядок записей в клиенте:

1. ``🔥 Auto (рекомендуемый)`` — при одном VLESS без ``whitelist``: ``vless://``; при
   нескольких — JSON balancer ``leastPing`` (Happ). В Clash — ``url-test`` по пулу.
   Узлы с ``include_in_auto=false`` в эти группы не входят (остаются отдельными строками).
2. ``📄 Auto (Белые списки)`` — то же для VLESS с ``whitelist``, если такие узлы есть.
3. Все узлы выдачи по одному разу с обычными именами: сначала без ``whitelist``,
   в конце списка — только с ``whitelist`` (внутри групп — по ``load_percent``).

Узлы с ``is_hidden=true`` в подписку не попадают (только админка / метрики / провижининг).

Каскад: внешние exit узлы из пар «РФ-вход → exit» в список не попадают
(``subscription_servers_for_delivery``).

Параметр ``fp`` (uTLS) в ``vless://`` и поле ``fingerprint`` в JSON узла: при каждой
выдаче подписки случайно выбирается из chrome / firefox / safari / edge (не из БД).
"""

from __future__ import annotations

import base64
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
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.build")

SUBSCRIPTION_AUTO_RECOMMENDED_LABEL = "🔥 Auto (рекомендуемый)"
SUBSCRIPTION_AUTO_WHITELIST_LABEL = "📄 Auto (Белые списки)"

_AUTO_BALANCER_TAG_PREFIX_REC = "auto-rec-"
_AUTO_BALANCER_TAG_PREFIX_WL = "auto-wl-"
_AUTO_BALANCER_PROBE_URL = "https://www.gstatic.com/generate_204"
_AUTO_BALANCER_PROBE_INTERVAL = "10s"

_HAPP_JSON_SNIFFING: dict[str, Any] = {
    "enabled": True,
    "destOverride": ["http", "tls", "quic"],
}
_HAPP_JSON_INBOUNDS: list[dict[str, Any]] = [
    {
        "tag": "socks",
        "port": 10808,
        "listen": "127.0.0.1",
        "protocol": "socks",
        "settings": {"udp": True, "auth": "noauth"},
        "sniffing": _HAPP_JSON_SNIFFING,
    },
    {
        "tag": "http",
        "port": 10809,
        "listen": "127.0.0.1",
        "protocol": "http",
        "sniffing": _HAPP_JSON_SNIFFING,
    },
]

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


def _vless_pool_for_auto(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
    *,
    whitelist: bool,
) -> list[Server]:
    """VLESS-узлы пула Auto с валидным URI (Hysteria2 не входит)."""
    return [
        s
        for s in ctx.delivery_rows
        if _is_vless_server(s)
        and bool(s.include_in_auto)
        and bool(s.whitelist) is whitelist
        and uri_by_id.get(s.id) is not None
    ]


def _auto_member_outbound_tag(server_id: int, *, whitelist: bool) -> str:
    prefix = _AUTO_BALANCER_TAG_PREFIX_WL if whitelist else _AUTO_BALANCER_TAG_PREFIX_REC
    return f"{prefix}{int(server_id)}"


def _auto_balancer_tag(*, whitelist: bool) -> str:
    return f"{_AUTO_BALANCER_TAG_PREFIX_WL}balancer" if whitelist else f"{_AUTO_BALANCER_TAG_PREFIX_REC}balancer"


def _server_to_vless_reality_outbound(
    s: Server,
    *,
    client_uuid: str,
    tag: str,
    client_fingerprint: str,
) -> dict[str, Any] | None:
    pbk = (s.reality_public_key or "").strip()
    if not pbk or "(" in pbk:
        return None
    sid = (s.reality_short_id or "").strip()
    if not sid:
        return None
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (client_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        return None
    host = (s.host or "").strip()
    uid = (client_uuid or "").strip()
    if not host or not uid:
        return None
    spx = normalize_reality_spider_x(s.reality_spider_x)
    stream_settings: dict[str, Any] = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "allowInsecure": False,
            "fingerprint": fp,
            "serverName": sni,
            "publicKey": pbk,
            "shortId": sid,
            "spiderX": spx,
            "show": False,
        },
        "tcpSettings": {"header": {"type": "none"}},
    }
    stream_settings.update(dict(_XRAY_VLESS_STREAM_SETTINGS_SOCKOPT))
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": int(s.port),
                    "users": [
                        {
                            "id": uid,
                            "encryption": "none",
                            "flow": flow,
                            "level": 8,
                            "security": "auto",
                        }
                    ],
                }
            ]
        },
        "streamSettings": stream_settings,
    }


def _happ_standard_outbound_tail() -> list[dict[str, Any]]:
    return [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ]


def _build_happ_multi_balancer_json(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    whitelist: bool,
) -> str | None:
    """
    Happ: JSON с inbounds, observatory и balancer ``leastPing`` (только при 2+ узлах в пуле).
    """
    if len(pool) < 2:
        return None
    balancer_tag = _auto_balancer_tag(whitelist=whitelist)
    member_tags: list[str] = []
    proxy_outbounds: list[dict[str, Any]] = []
    for s in pool:
        member_tag = _auto_member_outbound_tag(s.id, whitelist=whitelist)
        ob = _server_to_vless_reality_outbound(
            s,
            client_uuid=client_uuid,
            tag=member_tag,
            client_fingerprint=fp_by_id[s.id],
        )
        if ob is None:
            continue
        member_tags.append(member_tag)
        proxy_outbounds.append(ob)
    if len(member_tags) < 2:
        return None

    outbounds = [*proxy_outbounds, *_happ_standard_outbound_tail()]
    doc: dict[str, Any] = {
        "remarks": remark,
        "inbounds": list(_HAPP_JSON_INBOUNDS),
        "observatory": {
            "subjectSelector": list(member_tags),
            "probeUrl": _AUTO_BALANCER_PROBE_URL,
            "probeInterval": _AUTO_BALANCER_PROBE_INTERVAL,
            "enableConcurrency": True,
        },
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "balancerTag": balancer_tag,
                }
            ],
            "balancers": [
                {
                    "tag": balancer_tag,
                    "selector": list(member_tags),
                    "strategy": {"type": "leastPing"},
                    "fallbackTag": member_tags[0],
                }
            ],
        },
        "outbounds": outbounds,
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _append_happ_auto_subscription_entry(
    *,
    uris: list[str],
    servers_out: list[dict[str, Any]],
    remark: str,
    pool: list[Server],
    client_uuid: str,
    fp_by_id: dict[int, str],
    exit_ids_referenced: set[int],
    whitelist: bool,
) -> None:
    """
    Auto в теле подписки.

    - 1 узел: ``vless://`` (Happ стабильно импортирует share-ссылки; JSON без inbounds — нет).
    - 2+ узла: JSON balancer + локальные inbounds.
    """
    if not pool:
        return

    if len(pool) == 1:
        s = pool[0]
        fp = fp_by_id[s.id]
        uri = _vless_reality_share_uri(
            s,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            client_fingerprint=fp,
            fragment_override=remark,
        )
        if not uri:
            return
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=exit_ids_referenced,
                client_fingerprint=fp,
                name_override=remark,
            )
        )
        uris.append(uri)
        return

    line = _build_happ_multi_balancer_json(
        remark,
        pool,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        whitelist=whitelist,
    )
    if not line:
        return
    servers_out.append(
        _balancer_to_subscription_dict(remark, pool, whitelist=whitelist),
    )
    uris.append(line)


def _balancer_to_subscription_dict(
    remark: str,
    pool: list[Server],
    *,
    whitelist: bool,
) -> dict[str, Any]:
    member_ids = [int(s.id) for s in pool]
    if len(member_ids) == 1:
        return {
            "name": remark,
            "protocol": "vless",
            "whitelist": whitelist,
            "member_server_ids": member_ids,
        }
    return {
        "name": remark,
        "protocol": "balancer",
        "strategy": "leastPing",
        "whitelist": whitelist,
        "member_server_ids": member_ids,
    }


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
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)

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

    _append_url_test_group(SUBSCRIPTION_AUTO_RECOMMENDED_LABEL, pool_rec)
    if any(s.whitelist for s in ctx.delivery_rows if _is_vless_server(s)):
        _append_url_test_group(SUBSCRIPTION_AUTO_WHITELIST_LABEL, pool_wl)

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
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)
    any_whitelist_vless = any(
        s.whitelist for s in ctx.delivery_rows if _is_vless_server(s)
    )

    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []

    _append_happ_auto_subscription_entry(
        uris=uris,
        servers_out=servers_out,
        remark=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        pool=pool_rec,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        exit_ids_referenced=ctx.exit_ids_referenced,
        whitelist=False,
    )

    if any_whitelist_vless:
        _append_happ_auto_subscription_entry(
            uris=uris,
            servers_out=servers_out,
            remark=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            pool=pool_wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            exit_ids_referenced=ctx.exit_ids_referenced,
            whitelist=True,
        )

    for s in ctx.delivery_rows:
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                client_fingerprint=fp_by_id[s.id],
            )
        )
        u = uri_by_id.get(s.id)
        if u:
            uris.append(u)

    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )
