import re
import uuid as uuid_lib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServersCountResponse(BaseModel):
    servers_count: int = Field(ge=0, description="Число записей в таблице servers")


class ServerCreate(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=256,
        description="Подпись в админке (необязательно)",
    )
    host: str = Field(
        min_length=1,
        max_length=512,
        description="IP или доменное имя узла",
    )
    port: int = Field(
        default=443,
        ge=1,
        le=65535,
        description="Порт inbound (VLESS REALITY)",
    )
    country: str = Field(
        min_length=1,
        max_length=128,
        description="Страна (код ISO, название или метка для клиента)",
    )
    load_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Оценка загрузки 0–100 (для сортировки/отбора при выдаче подписки)",
    )
    is_active: bool = Field(default=True, description="Учитывать узел при выдаче подписки")
    vless_uuid: str | None = Field(
        default=None,
        max_length=64,
        description="UUID клиента VLESS; пусто — сгенерировать",
    )
    reality_short_id: str | None = Field(
        default=None,
        max_length=32,
        description="shortId REALITY (hex); пусто — сгенерировать",
    )
    reality_dest: str | None = Field(
        default=None,
        max_length=256,
        description="dest REALITY host:port (маскировка), по умолчанию Amazon",
    )
    reality_server_names: str | None = Field(
        default=None,
        max_length=512,
        description="serverNames через запятую; по умолчанию домены Amazon",
    )
    reality_fingerprint: str | None = Field(
        default=None,
        max_length=64,
        description="uTLS fingerprint, по умолчанию chrome",
    )
    vless_flow: str | None = Field(
        default=None,
        max_length=64,
        description="flow для tcp+xtls, по умолчанию xtls-rprx-vision",
    )
    prometheus_instance: str | None = Field(
        default=None,
        max_length=256,
        description="Label instance в Prometheus (node_exporter), напр. 1.2.3.4:9100; пусто — host:9100",
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("host", mode="before")
    @classmethod
    def normalize_host(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("host: не может быть пустым")
        return s

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("country: укажите страну")
        return s

    @field_validator("vless_uuid", mode="before")
    @classmethod
    def normalize_vless_uuid(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        try:
            uuid_lib.UUID(s)
        except ValueError as e:
            raise ValueError("vless_uuid: невалидный UUID") from e
        return s

    @field_validator("reality_short_id", mode="before")
    @classmethod
    def normalize_short_id(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        if not s:
            return None
        if not re.fullmatch(r"[0-9a-f]{2,16}", s):
            raise ValueError("reality_short_id: только hex, 2–16 символов")
        return s

    @field_validator("reality_dest", "reality_server_names", mode="before")
    @classmethod
    def strip_opt(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("reality_fingerprint", "vless_flow", mode="before")
    @classmethod
    def strip_small(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("prometheus_instance", mode="before")
    @classmethod
    def normalize_prom_instance(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class ServerUpdate(BaseModel):
    """Частичное обновление (админка: правка нагрузки и метаданных)."""

    name: str | None = Field(default=None, max_length=256)
    country: str | None = Field(default=None, max_length=128)
    load_percent: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    reality_dest: str | None = Field(default=None, max_length=256)
    reality_server_names: str | None = Field(default=None, max_length=512)
    reality_fingerprint: str | None = Field(default=None, max_length=64)
    vless_flow: str | None = Field(default=None, max_length=64)
    reality_short_id: str | None = Field(default=None, max_length=32)
    reality_private_key: str | None = Field(
        default=None,
        max_length=512,
        description="Приватный ключ REALITY (опционально); публичный пересчитается при установке",
    )
    prometheus_instance: str | None = Field(
        default=None,
        max_length=256,
        description="Prometheus instance (node_exporter); null — очистить, пустая строка — как null",
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            raise ValueError("country: не может быть пустым")
        return s

    @field_validator(
        "reality_dest",
        "reality_server_names",
        "reality_fingerprint",
        "vless_flow",
        mode="before",
    )
    @classmethod
    def strip_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("reality_short_id", mode="before")
    @classmethod
    def normalize_short_id_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        if not s:
            return None
        if not re.fullmatch(r"[0-9a-f]{2,16}", s):
            raise ValueError("reality_short_id: только hex, 2–16 символов")
        return s

    @field_validator("reality_private_key", mode="before")
    @classmethod
    def normalize_priv(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("prometheus_instance", mode="before")
    @classmethod
    def normalize_prom_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    host: str
    port: int
    country: str
    load_percent: int
    is_active: bool
    provision_ready: bool = Field(description="ПО на узле установлено (воркер завершил задачу)")
    provision_status: str = Field(
        description="idle | queued | running | success | failed",
    )
    provision_error: str | None = Field(description="Текст ошибки при failed")
    provision_job_id: str | None = Field(description="ID последней задачи RQ")
    vless_uuid: str
    reality_private_key: str | None
    reality_public_key: str | None
    reality_short_id: str
    reality_dest: str
    reality_server_names: str
    reality_fingerprint: str
    vless_flow: str
    prometheus_instance: str | None = Field(
        default=None,
        description="Цель Prometheus (label instance) для метрик node_exporter",
    )
