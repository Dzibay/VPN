from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.dependencies import ReadonlySessionDep, require_admin
from app.domain.models.status import StatusResponse
from app.domain.services.status_service import db_ping_ok

router = APIRouter(tags=["admin"])


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Состояние сервиса и доступность базы данных",
    dependencies=[Depends(require_admin)],
)
async def server_status(session: ReadonlySessionDep) -> StatusResponse:
    return StatusResponse(
        service=settings.app_name,
        status="running",
        debug=settings.debug,
        db_connected=db_ping_ok(session),
    )
