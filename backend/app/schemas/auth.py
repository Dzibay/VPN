from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "user", "manager"] = Field(
        description="Роль в JWT: admin и manager соответствуют account_role в БД; user — клиентская запись (account_role=client).",
    )


class TelegramAuthTokenResponse(TokenResponse):
    is_new_user: bool = Field(
        description=(
            "True, если в этом запросе создана новая учётная запись по telegram_id "
            "(первая регистрация). False — пользователь уже существовал или повтор после гонки вставки."
        ),
    )
