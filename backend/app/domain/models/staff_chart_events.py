import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StaffChartEventCreate(BaseModel):
    event_at: datetime = Field(description="Момент события (с часовым поясом или UTC)")
    title: str = Field(min_length=1, max_length=500)
    color: str = Field(
        min_length=7,
        max_length=7,
        description="Цвет в формате #RRGGBB",
    )

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title не может быть пустым")
        return s

    @field_validator("color")
    @classmethod
    def normalize_hex_color(cls, v: str) -> str:
        s = v.strip()
        if not _HEX_COLOR.match(s):
            raise ValueError("color: ожидается #RRGGBB")
        return s.upper()


class StaffChartEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(ge=1)
    event_at: datetime
    title: str
    color: str
    created_at: datetime
