"""Публичное описание VPN-клиента для страницы /apps/{code} (без токена подписки)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClientAppPublicResponse(BaseModel):
    client_code: str
    display_name: str
    store_links: dict[str, dict[str, str | None]] = Field(
        default_factory=dict,
        description="Платформы → site | download (как AppStoreLinks.to_public_json_dict).",
    )
