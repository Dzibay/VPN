"""Сборка тестовой подписки /test-sub: профили Happ (competitor JSON + vless)."""

from __future__ import annotations

import base64
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
    build_happ_competitor_balanced_profile_json,
)
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_sub_build")


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _append_competitor_profile(
    *,
    uris: list[str],
    remark: str,
    pool: list[Server],
    client_uuid: str,
    fp_by_id: dict[int, str],
    pool_whitelist: bool,
    fallback_server: Server | None = None,
    balancer_tag: str | None = None,
) -> None:
    kwargs: dict[str, Any] = {}
    if balancer_tag is not None:
        kwargs["balancer_tag"] = balancer_tag
    line = build_happ_competitor_balanced_profile_json(
        remark,
        pool,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=pool_whitelist,
        fallback_server=fallback_server,
        **kwargs,
    )
    if line:
        uris.append(line)


def build_test_sub_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """
    Подписка для Happ mobile (формат конкурентов).

    1. Auto (рекомендуемый) — один JSON: ``pool_rec`` + ``leastLoad`` + fallback на лучший WL.
    2. Auto (белые списки) — один JSON: ``pool_wl`` (balancer внутри профиля).
    3. Обычные узлы — ``vless://``.
    4. Каждый WL — JSON ``pool_rec`` + fallback на этот WL.
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

    if pool_rec:
        _append_competitor_profile(
            uris=uris,
            remark=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
            pool=pool_rec,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=False,
            fallback_server=best_wl,
        )

    if pool_wl:
        _append_competitor_profile(
            uris=uris,
            remark=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            pool=pool_wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=True,
            fallback_server=_best_server_by_load(pool_wl),
        )

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        u = uri_by_id.get(s.id)
        if u:
            uris.append(u)

    for wl in pool_wl:
        if not pool_rec:
            continue
        remark = _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced)
        _append_competitor_profile(
            uris=uris,
            remark=remark,
            pool=pool_rec,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            pool_whitelist=False,
            fallback_server=wl,
            balancer_tag=f"wl-{int(wl.id)}-balance",
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
