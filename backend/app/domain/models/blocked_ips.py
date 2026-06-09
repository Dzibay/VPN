from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.client_ip import normalize_ip_address


class BlockedIpCreate(BaseModel):
    ip: str = Field(min_length=1, max_length=45, description="IPv4 или IPv6")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("ip")
    @classmethod
    def normalize_ip(cls, v: str) -> str:
        return normalize_ip_address(v)

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class BlockedIpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(ge=1)
    ip: str
    note: str | None
    created_at: datetime
