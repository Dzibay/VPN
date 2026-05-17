"""Тестовые JSON-профили для Happ: какие форматы импортируются на mobile."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from app.domain.models.subscription import SubscriptionPayload
from app.domain.subscription.build import (
    _AUTO_BALANCER_PROBE_INTERVAL,
    _AUTO_BALANCER_PROBE_URL,
    _HAPP_JSON_INBOUNDS,
    _HAPP_JSON_SNIFFING,
    _auto_member_outbound_tag,
    _happ_standard_outbound_tail,
    _server_to_vless_reality_outbound,
    _subscription_delivery_context,
    _subscription_uri_and_fingerprint_by_server_id,
    _vless_pool_for_auto,
    _vless_reality_share_uri,
)
from app.domain.subscription.happ_mobile_json import build_happ_mobile_profile_json
from app.domain.subscription.happ_balancer_json import build_happ_balancer_json
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.subscription.test_happ_variants")

_CONTROL_VLESS_LABEL = "CONTROL vless (regular)"


def _inbounds_with_ports(socks_port: int, http_port: int) -> list[dict[str, Any]]:
    return [
        {
            "tag": "socks",
            "port": socks_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"udp": True, "auth": "noauth"},
            "sniffing": _HAPP_JSON_SNIFFING,
        },
        {
            "tag": "http",
            "port": http_port,
            "listen": "127.0.0.1",
            "protocol": "http",
            "sniffing": _HAPP_JSON_SNIFFING,
        },
    ]


def _rec_wl_outbounds(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
    rec_tag: str = "test-rec",
    wl_tag: str = "test-wl",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rec_ob = _server_to_vless_reality_outbound(
        rec,
        client_uuid=client_uuid,
        tag=rec_tag,
        client_fingerprint=fp_by_id[rec.id],
    )
    if rec_ob is None:
        return out
    out.append(rec_ob)
    if wl is not None:
        wl_ob = _server_to_vless_reality_outbound(
            wl,
            client_uuid=client_uuid,
            tag=wl_tag,
            client_fingerprint=fp_by_id[wl.id],
        )
        if wl_ob is not None:
            out.append(wl_ob)
    out.extend(_happ_standard_outbound_tail())
    return out


def _variant_01_full(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Как в /test-sub: inbounds + observatory + balancer + fallback."""
    pool = [rec]
    return build_happ_balancer_json(
        "TEST-01 full (prod format)",
        pool,
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=False,
        fallback_server=wl,
        balancer_tag="test-01-balancer",
    )


def _variant_02_outbounds_only(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str:
    """Только remarks + outbounds (без routing/inbounds/observatory)."""
    doc: dict[str, Any] = {
        "remarks": "TEST-02 outbounds only",
        "outbounds": _rec_wl_outbounds(
            rec, wl, client_uuid=client_uuid, fp_by_id=fp_by_id
        ),
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_03_routing_direct(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str:
    """routing → outboundTag на regular (без balancer)."""
    rec_tag = "test-rec"
    doc: dict[str, Any] = {
        "remarks": "TEST-03 routing direct",
        "outbounds": _rec_wl_outbounds(
            rec, wl, client_uuid=client_uuid, fp_by_id=fp_by_id, rec_tag=rec_tag
        ),
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": rec_tag,
                }
            ],
        },
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_04_inbounds_routing_direct(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str:
    """inbounds 10808/10809 + routing direct (без balancer/observatory)."""
    rec_tag = "test-rec"
    doc: dict[str, Any] = {
        "remarks": "TEST-04 inbounds+routing",
        "inbounds": list(_HAPP_JSON_INBOUNDS),
        "outbounds": _rec_wl_outbounds(
            rec, wl, client_uuid=client_uuid, fp_by_id=fp_by_id, rec_tag=rec_tag
        ),
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": rec_tag,
                }
            ],
        },
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_05_no_observatory(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Balancer + fallback, без observatory."""
    rec_tag = "test-rec"
    member_tags = [rec_tag]
    proxy_outbounds: list[dict[str, Any]] = []
    rec_ob = _server_to_vless_reality_outbound(
        rec,
        client_uuid=client_uuid,
        tag=rec_tag,
        client_fingerprint=fp_by_id[rec.id],
    )
    if rec_ob is None:
        return None
    proxy_outbounds.append(rec_ob)
    fallback_tag = rec_tag
    if wl is not None:
        wl_tag = "test-wl"
        wl_ob = _server_to_vless_reality_outbound(
            wl,
            client_uuid=client_uuid,
            tag=wl_tag,
            client_fingerprint=fp_by_id[wl.id],
        )
        if wl_ob is not None:
            proxy_outbounds.append(wl_ob)
            fallback_tag = wl_tag
    bal_tag = "test-05-balancer"
    doc: dict[str, Any] = {
        "remarks": "TEST-05 no observatory",
        "inbounds": list(_HAPP_JSON_INBOUNDS),
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
                    "selector": member_tags,
                    "strategy": {"type": "leastPing"},
                    "fallbackTag": fallback_tag,
                }
            ],
        },
        "outbounds": [*proxy_outbounds, *_happ_standard_outbound_tail()],
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_06_unique_ports(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Полный balancer; inbounds на 10810/10811 (нет конфликта с 10808)."""
    line = build_happ_balancer_json(
        "TEST-06 ports 10810",
        [rec],
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=False,
        fallback_server=wl,
        balancer_tag="test-06-balancer",
    )
    if line is None:
        return None
    doc = json.loads(line)
    doc["inbounds"] = _inbounds_with_ports(10810, 10811)
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_07_pretty_json(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Тот же full, но с отступами (не minified)."""
    line = build_happ_balancer_json(
        "TEST-07 pretty JSON",
        [rec],
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=False,
        fallback_server=wl,
        balancer_tag="test-07-balancer",
    )
    if line is None:
        return None
    doc = json.loads(line)
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _variant_08_meta_block(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str:
    """remarks + meta (как в примерах Happ) + outbounds."""
    doc: dict[str, Any] = {
        "remarks": "TEST-08 meta block",
        "meta": {"serverDescription": "Happ variant 08"},
        "outbounds": _rec_wl_outbounds(
            rec, wl, client_uuid=client_uuid, fp_by_id=fp_by_id
        ),
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_09_single_outbound(
    rec: Server,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Один vless outbound, tag proxy (как в тестовых конфигах)."""
    rec_ob = _server_to_vless_reality_outbound(
        rec,
        client_uuid=client_uuid,
        tag="proxy",
        client_fingerprint=fp_by_id[rec.id],
    )
    if rec_ob is None:
        return None
    doc: dict[str, Any] = {
        "remarks": "TEST-09 tag proxy",
        "outbounds": [rec_ob, *_happ_standard_outbound_tail()],
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _variant_10_emoji_remark(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Full + emoji в remarks (проверка UTF-8)."""
    return build_happ_balancer_json(
        "TEST-10 emoji 🔥📄🇳🇱",
        [rec],
        client_uuid=client_uuid,
        fp_by_id=fp_by_id,
        pool_whitelist=False,
        fallback_server=wl,
        balancer_tag="test-10-balancer",
    )


def _variant_11_happ_mobile_format(
    rec: Server,
    wl: Server | None,
    *,
    client_uuid: str,
    fp_by_id: dict[int, str],
) -> str | None:
    """Как сторонние VPN: dns + log + inbounds + proxy + routing (без balancer)."""
    _ = wl
    return build_happ_mobile_profile_json(
        "TEST-11 happ mobile (like other VPN)",
        rec,
        client_uuid=client_uuid,
        client_fingerprint=fp_by_id[rec.id],
        server_description="VLESS",
    )


def build_test_happ_variants_payload(user: User, rows: list[Server]) -> SubscriptionPayload:
    """
    Подписка только для диагностики Happ mobile.

    Строки:
    - комментарий ``# ...`` (игнорируется клиентом);
    - ``CONTROL vless`` — эталонная share-ссылка (должна быть видна всегда);
    - TEST-01 … TEST-11 — варианты JSON.
    """
    ctx = _subscription_delivery_context(rows)
    client_uuid = (user.vless_uuid or "").strip()
    uri_by_id, fp_by_id = _subscription_uri_and_fingerprint_by_server_id(
        ctx, client_uuid=client_uuid
    )
    pool_rec = _vless_pool_for_auto(ctx, uri_by_id, whitelist=False)
    pool_wl = _vless_pool_for_auto(ctx, uri_by_id, whitelist=True)
    rec = pool_rec[0] if pool_rec else None
    wl = pool_wl[0] if pool_wl else None

    if rec is None:
        raise ValueError("Нужен хотя бы один regular VLESS с include_in_auto для тестовых JSON")

    builders: list[tuple[str, Any]] = [
        ("01", _variant_01_full),
        ("02", _variant_02_outbounds_only),
        ("03", _variant_03_routing_direct),
        ("04", _variant_04_inbounds_routing_direct),
        ("05", _variant_05_no_observatory),
        ("06", _variant_06_unique_ports),
        ("07", _variant_07_pretty_json),
        ("08", _variant_08_meta_block),
        ("09", _variant_09_single_outbound),
        ("10", _variant_10_emoji_remark),
        ("11", _variant_11_happ_mobile_format),
    ]

    uris: list[str] = [
        "# Happ JSON variants: compare with CONTROL vless on phone",
        "# Expected on mobile: TEST-11 (like other VPN); old balancer: TEST-01..10",
    ]

    control = _vless_reality_share_uri(
        rec,
        client_uuid=client_uuid,
        exit_ids_referenced=ctx.exit_ids_referenced,
        client_fingerprint=fp_by_id[rec.id],
        fragment_override=_CONTROL_VLESS_LABEL,
    )
    if control:
        uris.append(control)

    for _num, fn in builders:
        try:
            if fn is _variant_09_single_outbound:
                line = fn(rec, client_uuid=client_uuid, fp_by_id=fp_by_id)
            else:
                line = fn(
                    rec,
                    wl,
                    client_uuid=client_uuid,
                    fp_by_id=fp_by_id,
                )
        except Exception as exc:
            log.warning("Skip happ variant %s: %s", _num, exc)
            continue
        if line:
            uris.append(line)

    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=[],
        vless_uris=uris,
        subscription_base64=b64,
    )
