from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="Состояние сервиса", examples=["ok"])
    admin_api_requires_jwt: bool = Field(
        description=(
            "True, если защищённые админ-эндпоинты требуют Bearer JWT "
            "(тот же признак, что jwt_gate_active() в зависимостях API)."
        ),
    )
