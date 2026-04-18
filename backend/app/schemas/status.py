from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="Состояние сервиса", examples=["ok"])


class StatusResponse(BaseModel):
    service: str
    status: str = Field(description="Режим работы API", examples=["running"])
    debug: bool
    db_connected: bool = Field(
        description="Успешный запрос к PostgreSQL (таблица users)",
    )
