"""
Кодирование тела подписки для Happ.

Стандартная подписка (v2rayNG и др.): Base64(текст со строками ``vless://`` …).

Happ «JSON array» (как у vpnhub): тело ответа — **сырой** ``[{...},{...}]``,
``Content-Type: application/json`` (без дополнительного Base64 поверх массива).
``json_array_b64`` — эксперимент; Happ mobile на нём падает с ошибкой импорта.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

HappSubscriptionBodyFormat = Literal[
    "lines",
    "json_array_b64",
    "json_array_raw",
    "json_array_mixed",
]


def parse_json_profile_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        doc = json.loads(line)
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) else None


def encode_happ_subscription_body(
    *,
    fmt: HappSubscriptionBodyFormat,
    json_profiles: list[dict[str, Any]] | None = None,
    text_lines: list[str] | None = None,
    ordered_lines: list[str] | None = None,
) -> tuple[str, str]:
    """
    Возвращает ``(тело ответа, Content-Type)``.

    ``json_array_raw`` — ``application/json``, массив JSON-профилей.
    ``json_array_mixed`` — ``application/json``: сначала объекты-профили, затем строки ``vless://`` / ``hysteria2://``.
    ``json_array_b64`` — Base64(JSON array) в text/plain (Happ не принимает).
    ``lines`` — Base64 построчно (см. ``ordered_lines`` для явного порядка).
    ``ordered_lines`` — готовый список строк (JSON-строки и ``vless://``); Happ их импортирует из Base64.
  """
    if ordered_lines is not None:
        raw = "\n".join(ordered_lines) + ("\n" if ordered_lines else "")
        body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
        return body, "text/plain; charset=utf-8"

    profiles = json_profiles or []

    if fmt == "lines":
        lines: list[str] = list(text_lines or [])
        for doc in profiles:
            lines.append(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        raw = "\n".join(lines) + ("\n" if lines else "")
        body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
        return body, "text/plain; charset=utf-8"

    if fmt == "json_array_raw":
        raw = json.dumps(profiles, ensure_ascii=False, separators=(",", ":"))
        return raw, "application/json; charset=utf-8"

    if fmt == "json_array_mixed":
        items: list[Any] = [*profiles]
        items.extend(text_lines or [])
        raw = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return raw, "application/json; charset=utf-8"

    # json_array_b64
    raw = json.dumps(json_profiles, ensure_ascii=False, separators=(",", ":"))
    body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
    return body, "text/plain; charset=utf-8"
