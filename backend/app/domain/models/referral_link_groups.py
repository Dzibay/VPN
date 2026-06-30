import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

GROUP_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
DEFAULT_GROUP_COLOR = "#58d68d"


class ReferralLinkGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    sort_order: int
    created_at: datetime
    link_ids: list[int] = Field(
        default_factory=list,
        description="referral_links.id, входящие в группу",
    )


class ReferralLinkGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=7)
    link_ids: list[int] = Field(default_factory=list)
    sort_order: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("name: ожидается строка")
        s = v.strip()
        if not s:
            raise ValueError("name не может быть пустым")
        return s

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("color: ожидается строка")
        s = v.strip()
        if not s:
            return None
        if not GROUP_COLOR_PATTERN.fullmatch(s):
            raise ValueError("color: ожидается #RRGGBB")
        return s.lower()

    @field_validator("link_ids")
    @classmethod
    def unique_link_ids(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for raw in v:
            n = int(raw)
            if n < 1:
                raise ValueError("link_ids: id должен быть >= 1")
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out


class ReferralLinkGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=7)
    sort_order: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name_upd(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("name: ожидается строка")
        s = v.strip()
        if not s:
            raise ValueError("name не может быть пустым")
        return s

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color_upd(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("color: ожидается строка")
        s = v.strip()
        if not s:
            return None
        if not GROUP_COLOR_PATTERN.fullmatch(s):
            raise ValueError("color: ожидается #RRGGBB")
        return s.lower()

    def at_least_one_field(self) -> "ReferralLinkGroupUpdate":
        if self.name is None and self.color is None and self.sort_order is None:
            raise ValueError("Укажите хотя бы одно поле")
        return self


class ReferralLinkGroupMembersBody(BaseModel):
    link_ids: list[int] = Field(default_factory=list)

    @field_validator("link_ids")
    @classmethod
    def unique_link_ids(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for raw in v:
            n = int(raw)
            if n < 1:
                raise ValueError("link_ids: id должен быть >= 1")
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out
