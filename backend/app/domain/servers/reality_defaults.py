"""Значения по умолчанию для VLESS+REALITY на новых узлах.

Любое поле, не заданное при создании сервера в админке, получает безопасное значение
отсюда: с дефолтными REALITY-параметрами (``amazon.com``) трафик в Wireshark выглядит как
обычный TLS до AWS. Если нужен другой ``reality_dest``, задайте поле явно при ``POST /servers``.
"""

from __future__ import annotations

import secrets
import uuid as uuid_lib

from app.domain.models.servers import ServerCreate

REALITY_DEFAULT_DEST = "www.amazon.com:443"
REALITY_DEFAULT_SERVER_NAMES = "www.amazon.com,amazon.com"
REALITY_DEFAULT_FINGERPRINT = "chrome"
VLESS_DEFAULT_FLOW = "xtls-rprx-vision"
REALITY_SHORT_ID_BYTES = 4


def reality_defaults_for_create(body: ServerCreate) -> dict[str, str]:
    """Подставить дефолты для незаданных REALITY/Xray-полей при создании сервера."""
    return {
        "vless_uuid": body.vless_uuid or str(uuid_lib.uuid4()),
        "reality_short_id": body.reality_short_id or secrets.token_hex(REALITY_SHORT_ID_BYTES),
        "reality_dest": body.reality_dest or REALITY_DEFAULT_DEST,
        "reality_server_names": body.reality_server_names or REALITY_DEFAULT_SERVER_NAMES,
        "reality_fingerprint": body.reality_fingerprint or REALITY_DEFAULT_FINGERPRINT,
        "vless_flow": body.vless_flow or VLESS_DEFAULT_FLOW,
    }
