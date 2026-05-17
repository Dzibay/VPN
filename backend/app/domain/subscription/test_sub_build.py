"""Сборка тестовой подписки /test-sub: Auto с fallback на WL и per-WL профили."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from app.domain.models.subscription import SubscriptionPayload
from app.domain.subscription.build import (
    SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
    SUBSCRIPTION_AUTO_WHITELIST_LABEL,
    _AUTO_BALANCER_PROBE_INTERVAL,
    _AUTO_BALANCER_PROBE_URL,
    _HAPP_JSON_INBOUNDS,
    _auto_balancer_tag,
    _auto_member_outbound_tag,
    _happ_standard_outbound_tail,
    _node_subscription_label,
    _server_to_subscription_dict,
    _server_to_vless_reality_outbound,
    _subscription_delivery_context,
    _subscription_uri_and_fingerprint_by_server_id,
    _vless_pool_for_auto,
    _vless_reality_share_uri,
)
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_sub_build")


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _build_happ_balancer_json(
    remark: str,
    pool: list[Server],
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    pool_whitelist: bool,
    fallback_server: Server | None = None,
    balancer_tag: str | None = None,
) -> str | None:
    """
    JSON balancer ``leastPing``.

    При 2+ узлах в пуле — полноценный balancer. При одном узле и ``fallback_server`` —
    один outbound в ``selector`` + ``fallbackTag`` на WL (tiered fallback без leastPing между regular).
    """
    if not pool:
        return None
    allow_single_member = fallback_server is not None
    if len(pool) < 2 and not allow_single_member:
        return None

    bal_tag = balancer_tag or _auto_balancer_tag(whitelist=pool_whitelist)
    member_tags: list[str] = []
    proxy_outbounds: list[dict[str, Any]] = []

    for s in pool:
        member_tag = _auto_member_outbound_tag(s.id, whitelist=pool_whitelist)
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

    if len(member_tags) < 1:
        return None
    if len(member_tags) < 2 and not allow_single_member:
        return None

    fallback_tag = member_tags[0]
    if fallback_server is not None:
        fb_tag = _auto_member_outbound_tag(fallback_server.id, whitelist=True)
        fb_ob = _server_to_vless_reality_outbound(
            fallback_server,
            client_uuid=client_uuid,
            tag=fb_tag,
            client_fingerprint=fp_by_id[fallback_server.id],
        )
        if fb_ob is not None:
            proxy_outbounds.append(fb_ob)
            fallback_tag = fb_tag

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
                    "balancerTag": bal_tag,
                }
            ],
            "balancers": [
                {
                    "tag": bal_tag,
                    "selector": list(member_tags),
                    "strategy": {"type": "leastPing"},
                    "fallbackTag": fallback_tag,
                }
            ],
        },
        "outbounds": outbounds,
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _append_balancer_or_vless(
    *,
    uris: list[str],
    remark: str,
    pool: list[Server],
    client_uuid: str,
    fp_by_id: dict[int, str],
    exit_ids_referenced: set[int],
    pool_whitelist: bool,
    fallback_server: Server | None = None,
    balancer_tag: str | None = None,
) -> None:
    if not pool:
        return

    if len(pool) == 1 and fallback_server is None:
        s = pool[0]
        uri = _vless_reality_share_uri(
            s,
            client_uuid=client_uuid,
            exit_ids_referenced=exit_ids_referenced,
            client_fingerprint=fp_by_id[s.id],
            fragment_override=remark,
        )
        if uri:
            uris.append(uri)
        return

    line = _build_happ_balancer_json(
        remark,
        pool,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=pool_whitelist,
        fallback_server=fallback_server,
        balancer_tag=balancer_tag,
    )
    if line:
        uris.append(line)


def _append_pool_rec_with_wl_fallback(
    *,
    uris: list[str],
    remark: str,
    pool_rec: list[Server],
    best_wl: Server | None,
    client_uuid: str,
    fp_by_id: dict[int, str],
    exit_ids_referenced: set[int],
    balancer_tag: str | None = None,
) -> None:
    """``pool_rec`` (2+ → balancer, 1 → JSON/vless) + ``fallbackTag`` на ``best_wl``."""
    if not pool_rec:
        return
    _append_balancer_or_vless(
        uris=uris,
        remark=remark,
        pool=pool_rec,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        exit_ids_referenced=exit_ids_referenced,
        pool_whitelist=False,
        fallback_server=best_wl,
        balancer_tag=balancer_tag,
    )


def build_test_sub_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """
    Порядок строк в Base64-подписке (только ``include_in_auto`` в пулах).

    ``pool_rec`` / ``pool_wl`` — VLESS с ``include_in_auto``; ``best_rec`` / ``best_wl`` — минимум
    ``load_percent`` в соответствующем пуле.

    1. Auto (рекомендуемый) — ``pool_rec``, fallback ``best_wl``.
    2. Auto (белые списки) — ``pool_rec``, fallback ``best_wl``.
    3. Обычные узлы — все без ``whitelist``, по одной ``vless://`` (без balancer).
    4. Серверы белых списков — для каждого из ``pool_wl``: ``pool_rec``, fallback на этот WL.
    """
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)
    best_wl = _best_server_by_load(pool_wl)

    uris: list[str] = []

    _append_pool_rec_with_wl_fallback(
        uris=uris,
        remark=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        pool_rec=pool_rec,
        best_wl=best_wl,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        exit_ids_referenced=ctx.exit_ids_referenced,
    )

    if pool_rec:
        _append_pool_rec_with_wl_fallback(
            uris=uris,
            remark=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            pool_rec=pool_rec,
            best_wl=best_wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            exit_ids_referenced=ctx.exit_ids_referenced,
            balancer_tag=_auto_balancer_tag(whitelist=True),
        )

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        u = uri_by_id.get(s.id)
        if u:
            uris.append(u)

    for wl in pool_wl:
        remark = _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced)
        _append_pool_rec_with_wl_fallback(
            uris=uris,
            remark=remark,
            pool_rec=pool_rec,
            best_wl=wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            exit_ids_referenced=ctx.exit_ids_referenced,
            balancer_tag=f"test-per-wl-{int(wl.id)}-balancer",
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

    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )
