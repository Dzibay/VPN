"""Сборка тестовой подписки GET /sub/test-sub (Happ JSON array)."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.models.subscription import SubscriptionPayload
from app.domain.subscription.build import (
    SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
    SUBSCRIPTION_AUTO_WHITELIST_LABEL,
    _node_subscription_label,
    _server_to_subscription_dict,
    _subscription_delivery_context,
    _subscription_uri_and_fingerprint_by_server_id,
    _vless_pool_for_auto,
)
from app.domain.subscription.happ_competitor_json import (
    build_happ_competitor_balanced_profile,
    build_happ_plain_vless_profile,
)
from app.domain.subscription.happ_subscription_encode import encode_happ_subscription_body
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_sub_build")


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _append_auto_profile(
    profiles: list[dict[str, Any]],
    *,
    remark: str,
    pool_rec: list[Server],
    best_wl: Server | None,
    client_uuid: str,
    fp_by_id: dict[int, str],
    balancer_tag: str,
) -> None:
    if not pool_rec:
        return
    doc = build_happ_competitor_balanced_profile(
        remark,
        pool_rec,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=False,
        fallback_server=best_wl,
        balancer_tag=balancer_tag,
    )
    if doc:
        profiles.append(doc)


def build_test_sub_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """
    Порядок профилей в JSON array (``application/json``):

    1. Auto (рекомендуемый) — ``pool_rec``, fallback ``best_wl``.
    2. Auto (белые списки) — ``pool_rec``, fallback ``best_wl``.
    3. Обычные узлы — по одному профилю на сервер (без balancer).
    4. Каждый ``pool_wl`` — ``pool_rec``, fallback на этот WL.
    """
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)
    best_wl = _best_server_by_load(pool_wl)

    profiles: list[dict[str, Any]] = []

    _append_auto_profile(
        profiles,
        remark=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
        pool_rec=pool_rec,
        best_wl=best_wl,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        balancer_tag="auto-rec-balance",
    )
    _append_auto_profile(
        profiles,
        remark=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
        pool_rec=pool_rec,
        best_wl=best_wl,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        balancer_tag="auto-wl-balance",
    )

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        doc = build_happ_plain_vless_profile(
            _node_subscription_label(s, exit_ids_referenced=ctx.exit_ids_referenced),
            s,
            client_uuid=client_uuid,
            client_fingerprint=fp_by_id[s.id],
        )
        if doc:
            profiles.append(doc)

    for wl in pool_wl:
        if not pool_rec:
            continue
        remark = _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced)
        _append_auto_profile(
            profiles,
            remark=remark,
            pool_rec=pool_rec,
            best_wl=wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            balancer_tag=f"wl-{int(wl.id)}-balance",
        )

    body, media_type = encode_happ_subscription_body(
        fmt="json_array_raw",
        json_profiles=profiles,
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
        vless_uris=[p.get("remarks", "json") for p in profiles if p.get("remarks")],
        subscription_base64=body,
        subscription_media_type=media_type,
    )
