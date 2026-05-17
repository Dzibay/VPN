"""JSON balancer (observatory + leastPing) — для desktop Happ; mobile не импортирует."""

from __future__ import annotations

import json
from typing import Any

from app.domain.subscription.build import (
    _AUTO_BALANCER_PROBE_INTERVAL,
    _AUTO_BALANCER_PROBE_URL,
    _HAPP_JSON_INBOUNDS,
    _auto_balancer_tag,
    _auto_member_outbound_tag,
    _happ_standard_outbound_tail,
    _server_to_vless_reality_outbound,
)
from app.infrastructure.persistence.models.server import Server


def build_happ_balancer_json(
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
    один outbound в ``selector`` + ``fallbackTag`` на WL.
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
