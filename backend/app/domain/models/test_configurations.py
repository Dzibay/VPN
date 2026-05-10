"""Записи тестовых клиентских конфигураций (файл configurations/test_configurations.json → /sub/test-configurations)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TestConfigurationItem(BaseModel):
    """Одна запись: стабильный id, опциональный заголовок для списка, полный JSON конфигурации."""

    id: str = Field(min_length=1, description="Уникальный ключ в пределах файла (в JSON допускается число — будет приведено к строке).")

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id_to_str(cls, v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        return v if isinstance(v, str) else str(v)
    title: str | None = Field(
        default=None,
        description="Подпись в списке; если не задано — используются remarks из config.",
    )
    config: dict[str, Any] = Field(
        description="Полная клиентская конфигурация (например экспорт для V2Ray/Xray).",
    )
