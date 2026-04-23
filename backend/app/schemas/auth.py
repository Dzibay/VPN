from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "user"] = Field(
        description="admin — учётная запись из env; user — запись в БД",
    )
