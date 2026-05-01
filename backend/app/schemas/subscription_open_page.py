"""Данные для SPA-страницы открытия подписки во внешнем клиенте (GET /sub/.../open/.../data)."""

from __future__ import annotations

from typing import Literal

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
