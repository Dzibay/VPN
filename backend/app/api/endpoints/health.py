from fastapi import APIRouter

from app.schemas.status import HealthResponse

router = APIRouter(tags=["public"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка живости сервиса",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
