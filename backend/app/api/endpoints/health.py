from fastapi import APIRouter

from app.schemas.status import HealthResponse

router = APIRouter(tags=["public"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка работоспособности процесса API без обращения к базе данных",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
