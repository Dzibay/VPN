from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="Состояние сервиса", examples=["ok"])
    admin_api_requires_jwt: bool = Field(
        description=(
            "True, если защищённые админ-эндпоинты требуют Bearer JWT "
            "(тот же признак, что jwt_gate_active() в зависимостях API)."
        ),
    )


class StatusResponse(BaseModel):
    service: str
    status: str = Field(description="Режим работы API", examples=["running"])
    debug: bool
    db_connected: bool = Field(
        description="Успешный запрос к PostgreSQL (таблица users)",
    )
