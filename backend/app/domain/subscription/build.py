"""Сборка тела подписки: список узлов, ``vless://`` URI, Base64, Clash Meta YAML.

Порядок записей в клиенте:

1. ``⚡ Auto (рекомендуемый)`` — дубликат первого узла в выдаче с валидным URI
   (список уже отсортирован по ``load_percent``).
2. ``⚡ Auto (белый список)`` — если среди узлов выдачи есть хотя бы один с
   ``whitelist``, дубликат первого по нагрузке среди whitelist с валидным URI.
3. Все узлы выдачи по одному разу с обычными именами.

Каскад: внешние exit узлы из пар «РФ-вход → exit» в список не попадают
(``subscription_servers_for_delivery``).
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BRAND_NAME
from app.domain.models.subscription import SubscriptionPayload
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.build")

SUBSCRIPTION_AUTO_RECOMMENDED_LABEL = "🔥 Auto (рекомендуемый)"
SUBSCRIPTION_AUTO_WHITELIST_LABEL = "📄 Auto (белый список)"


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


def _server_to_subscription_dict(
    s: Server,
    *,
    client_uuid: str,
    exit_ids_referenced: set[int],
    name_override: str | None = None,
) -> dict[str, Any]:
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    uid = (client_uuid or "").strip()
    display_name = (
        name_override
        if name_override is not None
        else _node_subscription_label(s, exit_ids_referenced=exit_ids_referenced)
    )
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


def _subscription_standard_uri_by_server_id(
    ctx: _SubscriptionDeliveryContext,
    *,
    client_uuid: str,
) -> dict[int, str | None]:
    """Один расчёт стандартного URI на узел (без auto-подписей)."""
    out: dict[int, str | None] = {}
    for s in ctx.delivery_rows:
        out[s.id] = _vless_reality_share_uri(
            s,
            client_uuid=client_uuid,
            exit_ids_referenced=ctx.exit_ids_referenced,
        )
    return out


def _pick_auto_duplicate_servers(
    ctx: _SubscriptionDeliveryContext,
    uri_by_id: dict[int, str | None],
) -> tuple[Server | None, Server | None]:
    """
    Лучший по нагрузке среди всех с рабочим URI; среди whitelist — только если в выдаче
    есть хотя бы один узел с флагом whitelist.
    """
    any_whitelist_in_delivery = any(s.whitelist for s in ctx.delivery_rows)
    auto_rec: Server | None = None
    auto_wl: Server | None = None
    for s in ctx.delivery_rows:
        if uri_by_id.get(s.id) is None:
            continue
        if auto_rec is None:
            auto_rec = s
        if s.whitelist and auto_wl is None:
            auto_wl = s
    if not any_whitelist_in_delivery:
        auto_wl = None
    return auto_rec, auto_wl


def _append_clash_vless_proxy(
    proxies: list[dict[str, Any]],
    s: Server,
    *,
    client_uuid: str,
    clash_name: str,
) -> None:
    pbk = (s.reality_public_key or "").strip()
    sid = (s.reality_short_id or "").strip()
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (s.reality_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    host = (s.host or "").strip()
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
            },
            "client-fingerprint": fp,
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
    """Clash Meta: VLESS + REALITY; тот же порядок узлов, что и в Base64-подписке."""
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id = _subscription_standard_uri_by_server_id(ctx, client_uuid=client_uuid)
    auto_rec, auto_wl = _pick_auto_duplicate_servers(ctx, uri_by_id)

    proxies: list[dict[str, Any]] = []
    names_seen: dict[str, int] = {}

    if auto_rec is not None:
        _append_clash_vless_proxy(
            proxies,
            auto_rec,
            client_uuid=client_uuid,
            clash_name=_unique_clash_proxy_name(SUBSCRIPTION_AUTO_RECOMMENDED_LABEL, names_seen),
        )
    if auto_wl is not None:
        _append_clash_vless_proxy(
            proxies,
            auto_wl,
            client_uuid=client_uuid,
            clash_name=_unique_clash_proxy_name(SUBSCRIPTION_AUTO_WHITELIST_LABEL, names_seen),
        )

    for s in ctx.delivery_rows:
        if uri_by_id.get(s.id) is None:
            continue
        label = _node_subscription_label(s, exit_ids_referenced=ctx.exit_ids_referenced)
        name = _unique_clash_proxy_name(label, names_seen)
        _append_clash_vless_proxy(proxies, s, client_uuid=client_uuid, clash_name=name)

    group_name = BRAND_NAME
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
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id = _subscription_standard_uri_by_server_id(ctx, client_uuid=client_uuid)
    auto_rec, auto_wl = _pick_auto_duplicate_servers(ctx, uri_by_id)

    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []

    if auto_rec is not None:
        servers_out.append(
            _server_to_subscription_dict(
                auto_rec,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                name_override=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
            )
        )
        u = _vless_reality_share_uri(
            auto_rec,
            client_uuid=client_uuid,
            exit_ids_referenced=ctx.exit_ids_referenced,
            fragment_override=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        )
        if u:
            uris.append(u)

    if auto_wl is not None:
        servers_out.append(
            _server_to_subscription_dict(
                auto_wl,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
                name_override=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            )
        )
        u = _vless_reality_share_uri(
            auto_wl,
            client_uuid=client_uuid,
            exit_ids_referenced=ctx.exit_ids_referenced,
            fragment_override=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
        )
        if u:
            uris.append(u)

    for s in ctx.delivery_rows:
        servers_out.append(
            _server_to_subscription_dict(
                s,
                client_uuid=client_uuid,
                exit_ids_referenced=ctx.exit_ids_referenced,
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
