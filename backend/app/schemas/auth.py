from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "user", "manager"] = Field(
        description="JWT: admin — account_role=admin; manager — account_role=manager; user — клиент (client).",
    )
