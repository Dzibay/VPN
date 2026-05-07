"""Публичная подписка /sub и страница открытия во внешнем клиенте."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubscriptionOpenPageData(BaseModel):
    """Публичный ответ без секретов: только диплинк и ссылки на магазины."""

    state: Literal["ok", "invalid_token", "inactive"] = Field(
        ...,
        description="ok — можно открыть клиент (при неактивной подписке узлы будут пустыми до продления); invalid_token — нет пользователя; inactive — устаревшее значение, не используется.",
    )
    title: str = Field(..., description="document.title")
    headline: str = Field(..., description="Заголовок на странице (h1)")
    message: str | None = Field(
        None,
        description="Текст при invalid_token / inactive (основной абзац).",
    )
    deeplink: str | None = Field(None, description="Схема клиента для открытия; null если недоступно.")
    open_button_label: str = Field("", description="Подпись основной кнопки «Открыть в …».")
    lead: str | None = Field(
        None,
        description="Вводный абзац при state=ok и непустом deeplink.",
    )
    hint: str | None = Field(None, description="Подсказка под кнопками.")
    store_links: dict[str, dict[str, str | None]] | None = Field(
        None,
        description="Как в AppStoreLinks.to_public_json_dict(): windows|android|ios|macos|linux → site|download.",
    )
    forced_platform: str | None = Field(
        None,
        description="Нормализованный query platform или null (выбор по User-Agent на клиенте).",
    )


class SubscriptionPayload(BaseModel):
    """Ответ по токену подписки: срок, узлы и готовые ссылки для VPN-клиентов (VLESS+REALITY)."""

    valid_until: date | None = Field(
        description="Подписка действительна до (включительно, календарная дата), null — без ограничения",
    )
    subscription_active: bool = Field(
        description="Если false (срок истёк), servers / vless_uris / subscription_base64 пустые",
    )
    servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Активные узлы: address, port, uuid, flow, sni, fingerprint (случайный uTLS fp на выдачу), "
        "public_key, short_id, dest, server_names; stream_settings — фрагмент для Xray streamSettings (sockopt).",
    )
    vless_uris: list[str] = Field(
        default_factory=list,
        description="Стандартные share-ссылки vless:// (v2rayN, v2rayNG, Nekoray, Streisand и др.)",
    )
    subscription_base64: str = Field(
        default="",
        description="Base64 от UTF-8 текста: по одной vless-ссылке на строку (как тело «subscription URL»)",
    )
