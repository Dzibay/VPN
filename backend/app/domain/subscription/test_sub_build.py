"""Сборка тестовой подписки /test-sub: профили Happ mobile (полный Xray JSON)."""

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
from app.domain.subscription.happ_mobile_json import build_happ_mobile_profile_json
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_sub_build")


def _best_server_by_load(servers: list[Server]) -> Server | None:
    if not servers:
        return None
    return min(servers, key=lambda s: (int(s.load_percent), int(s.id)))


def _append_happ_mobile_json(
    *,
    uris: list[str],
    remark: str,
    server: Server,
    client_uuid: str,
    fp_by_id: dict[int, str],
    server_description: str | None = None,
) -> None:
    line = build_happ_mobile_profile_json(
        remark,
        server,
        client_uuid=client_uuid,
        client_fingerprint=fp_by_id[server.id],
        server_description=server_description,
    )
    if line:
        uris.append(line)


def build_test_sub_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """
    Подписка для Happ (в т.ч. mobile): полный Xray JSON на узел, без balancer/observatory.

    ``include_in_auto`` — только для пулов Auto; отдельные ``vless://`` — все обычные узлы.

    1. Auto (рекомендуемый) — лучший ``pool_rec``; при наличии WL — второй профиль WL fallback.
    2. Auto (белые списки) — лучший ``pool_wl``.
    3. Обычные узлы — ``vless://`` без ``whitelist``.
    4. Каждый ``pool_wl`` — отдельный JSON-профиль на этот WL.
    """
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)
    best_rec = _best_server_by_load(pool_rec)
    best_wl = _best_server_by_load(pool_wl)

    uris: list[str] = []

    if best_rec is not None:
        _append_happ_mobile_json(
            uris=uris,
            remark=SUBSCRIPTION_AUTO_RECOMMENDED_LABEL,
            server=best_rec,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            server_description="regular",
        )
        if best_wl is not None and int(best_wl.id) != int(best_rec.id):
            _append_happ_mobile_json(
                uris=uris,
                remark=f"{SUBSCRIPTION_AUTO_RECOMMENDED_LABEL} → WL",
                server=best_wl,
                client_uuid=client_uuid,
                fp_by_id=fp_by_id,
                server_description="whitelist fallback",
            )

    if best_wl is not None:
        _append_happ_mobile_json(
            uris=uris,
            remark=SUBSCRIPTION_AUTO_WHITELIST_LABEL,
            server=best_wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            server_description="whitelist",
        )

    for s in ctx.delivery_rows:
        if s.whitelist:
            continue
        u = uri_by_id.get(s.id)
        if u:
            uris.append(u)

    for wl in pool_wl:
        remark = _node_subscription_label(wl, exit_ids_referenced=ctx.exit_ids_referenced)
        _append_happ_mobile_json(
            uris=uris,
            remark=remark,
            server=wl,
            client_uuid=client_uuid,
            fp_by_id=fp_by_id,
            server_description="whitelist",
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
