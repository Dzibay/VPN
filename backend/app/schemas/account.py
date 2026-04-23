from datetime import date

from pydantic import BaseModel, EmailStr, Field


class AccountRegisterBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72, description="До 72 байт (ограничение bcrypt)")


class AccountLoginBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)


class AccountMeResponse(BaseModel):
    id: int
    email: str
    telegram_id: str | None = None
    subscription_until: date | None = None
    subscription_active: bool
    subscription_token: str = Field(
        description="Токен для URL подписки /sub/{token}",
    )
