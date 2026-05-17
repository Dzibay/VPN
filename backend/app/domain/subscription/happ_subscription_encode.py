"""
Кодирование тела подписки для Happ.

Стандартная подписка: Base64(текст со строками ``vless://`` …).

Happ mobile при **синхронизации** подписки не импортирует сырые строки ``{...}`` в теле —
только URI-схемы. Полные JSON-профили (как при вставке из буфера) нужно отдавать
массивом конфигураций: Base64(UTF-8 JSON array) — см. Happ «JSON array» subscription.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

HappSubscriptionBodyFormat = Literal["lines", "json_array_b64", "json_array_raw"]


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
    json_profiles: list[dict[str, Any]],
    text_lines: list[str] | None = None,
) -> tuple[str, str]:
    """
    Возвращает ``(тело ответа, Content-Type)``.

    ``json_array_b64`` — по умолчанию для Happ mobile (JSON array внутри Base64).
    ``lines`` — legacy: Base64(``vless://`` + сырой JSON построчно).
  """
    if fmt == "lines":
        lines: list[str] = list(text_lines or [])
        for doc in json_profiles:
            lines.append(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        raw = "\n".join(lines) + ("\n" if lines else "")
        body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
        return body, "text/plain; charset=utf-8"

    if fmt == "json_array_raw":
        raw = json.dumps(json_profiles, ensure_ascii=False, separators=(",", ":"))
        return raw, "application/json; charset=utf-8"

    # json_array_b64
    raw = json.dumps(json_profiles, ensure_ascii=False, separators=(",", ":"))
    body = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii")
    return body, "text/plain; charset=utf-8"
