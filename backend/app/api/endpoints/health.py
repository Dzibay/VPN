from fastapi import APIRouter

from app.core.dependencies import jwt_gate_active
from app.domain.models.status import HealthResponse

router = APIRouter(tags=["public"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка работоспособности процесса API без обращения к базе данных",
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        admin_api_requires_jwt=jwt_gate_active(),
    )
