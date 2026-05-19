"""Кодирование тела подписки: JSON array (Happ) или Base64 построчно (v2raytun и др.)."""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_subscription_json_array(
    profiles: list[dict[str, Any]],
) -> tuple[str, str]:
    """``application/json`` — сырой массив профилей."""
    body = json.dumps(profiles, ensure_ascii=False, separators=(",", ":"))
    return body, "application/json; charset=utf-8"


def encode_subscription_base64_lines(lines: list[str]) -> tuple[str, str]:
    """``text/plain`` Base64 — по одной share-ссылке или JSON-строке на строку."""
    raw = "\n".join(lines) + ("\n" if lines else "")
    body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
    return body, "text/plain; charset=utf-8"
