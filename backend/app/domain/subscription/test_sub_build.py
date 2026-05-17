"""Сборка тестовой подписки /test-sub для Happ (JSON array + competitor balancer)."""

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
)
from app.domain.subscription.happ_mobile_json import build_happ_mobile_profile
from app.domain.subscription.happ_subscription_encode import (
    HappSubscriptionBodyFormat,
    encode_happ_subscription_body,
)
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_sub_build")


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _collect_test_sub_json_profiles(
    *,
    ctx,
    pool_rec: list[Server],
    pool_wl: list[Server],
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    best_wl = _best_server_by_load(pool_wl)

    if pool_rec:
        doc = build_happ_competitor_balanced_profile(
            SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
            pool_rec,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=False,
            fallback_server=best_wl,
        )
        if doc:
            profiles.append(doc)

    if pool_wl:
        doc = build_happ_competitor_balanced_profile(
            SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            pool_wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=True,
            fallback_server=_best_server_by_load(pool_wl),
        )
        if doc:
            profiles.append(doc)

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        doc = build_happ_mobile_profile(
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
        doc = build_happ_competitor_balanced_profile(
            remark,
            pool_rec,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=False,
            fallback_server=wl,
            balancer_tag=f"wl-{int(wl.id)}-balance",
        )
        if doc:
            profiles.append(doc)

    return profiles


def build_test_sub_payload(
    user: User,
    rows: list[Server],
    *,
    happ_body: HappSubscriptionBodyFormat = "json_array_b64",
) -> SubscriptionPayload:
    """
    Подписка для Happ mobile: ``json_array_b64`` (массив JSON-профилей в Base64).

    ``happ_body=lines`` — legacy (``vless://`` + сырой JSON построчно; mobile игнорирует JSON).
    """
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)

    json_profiles = _collect_test_sub_json_profiles(
        ctx=ctx,
        pool_rec=pool_rec,
        pool_wl=pool_wl,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
    )

    vless_lines: list[str] = []
    if happ_body == "lines":
        for s in ctx.delivery_rows:
            if s.whitelist:
                continue
            u = uri_by_id.get(s.id)
            if u:
                vless_lines.append(u)

    body, media_type = encode_happ_subscription_body(
        fmt=happ_body,
        json_profiles=json_profiles,
        text_lines=vless_lines if happ_body == "lines" else None,
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

    vless_uris = (
        vless_lines
        if happ_body == "lines"
        else [
            p.get("remarks", "json")
            for p in json_profiles
            if isinstance(p.get("remarks"), str)
        ]
    )

    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=vless_uris,
        subscription_base64=body,
        subscription_media_type=media_type,
    )
