from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    password: str = Field(min_length=1, description="Пароль панели из ADMIN_PANEL_PASSWORD")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthStatusResponse(BaseModel):
    admin_auth_required: bool = Field(
        description="True, если на сервере задан ADMIN_PANEL_PASSWORD и API требует Bearer",
    )
