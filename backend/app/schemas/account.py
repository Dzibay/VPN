from datetime import date

from pydantic import BaseModel, EmailStr, Field


class AccountRegisterBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72, description="До 72 байт (ограничение bcrypt)")


class AccountLoginBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)


class AccountMeResponse(BaseModel):
    role: str = Field(description="user | admin")
    id: int | None = Field(default=None, description="Для admin не заполняется")
    email: str
    telegram_id: str | None = None
    subscription_until: date | None = None
    subscription_active: bool = False
    subscription_token: str = Field(
        default="",
        description="Токен для /sub/{token} (Base64) и /sub/{token}/json; для admin пусто",
    )
