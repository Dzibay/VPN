"""Значения по умолчанию для VLESS+REALITY на новых узлах.

Любое поле, не заданное при создании сервера в админке, получает безопасное значение
отсюда: с дефолтными REALITY-параметрами (``amazon.com``) трафик в Wireshark выглядит как
обычный TLS до AWS. Если нужен другой ``reality_dest``, задайте поле явно при ``POST /servers``.
"""

from __future__ import annotations

import secrets
import uuid as uuid_lib

from app.domain.models.servers import ServerCreate
from app.domain.servers.host_validation import normalize_grpc_service_name, normalize_ws_path

REALITY_DEFAULT_DEST = "www.amazon.com:443"
REALITY_DEFAULT_SERVER_NAMES = "www.amazon.com,amazon.com"
REALITY_DEFAULT_FINGERPRINT = "chrome"
REALITY_DEFAULT_SPIDER_X = "/"
VLESS_DEFAULT_FLOW = "xtls-rprx-vision"
REALITY_SHORT_ID_BYTES = 4
GRPC_DEFAULT_SERVICE_NAME = "grpc"
WS_DEFAULT_PATH = "/vless"


def normalize_reality_spider_x(raw: str | None) -> str:
    """Путь REALITY spiderX: ведущий «/», длина до 256 (как в Xray)."""
    s = (raw or "").strip() or REALITY_DEFAULT_SPIDER_X
    if not s.startswith("/"):
        s = "/" + s.lstrip("/")
    return s[:256]


def reality_defaults_for_create(body: ServerCreate) -> dict[str, str]:
    """Подставить дефолты для незаданных REALITY/Xray-полей при создании сервера."""
    out = {
        "vless_uuid": body.vless_uuid or str(uuid_lib.uuid4()),
        "reality_short_id": body.reality_short_id or secrets.token_hex(REALITY_SHORT_ID_BYTES),
        "reality_dest": body.reality_dest or REALITY_DEFAULT_DEST,
        "reality_server_names": body.reality_server_names or REALITY_DEFAULT_SERVER_NAMES,
        "reality_fingerprint": body.reality_fingerprint or REALITY_DEFAULT_FINGERPRINT,
        "reality_spider_x": normalize_reality_spider_x(body.reality_spider_x),
        "vless_flow": body.vless_flow or VLESS_DEFAULT_FLOW,
    }
    if body.proxy_kind in ("vless_grpc", "vless_ws"):
        host = (body.host or "").strip()
        tls_sni = (body.tls_sni or host).strip()
        out["tls_sni"] = tls_sni or host
    if body.proxy_kind == "vless_grpc":
        out["grpc_service_name"] = normalize_grpc_service_name(
            body.grpc_service_name or GRPC_DEFAULT_SERVICE_NAME
        )
    if body.proxy_kind == "vless_ws":
        out["ws_path"] = normalize_ws_path(body.ws_path or WS_DEFAULT_PATH)
    return out
