from fastapi import APIRouter, Depends

from app.api.deps import ReadonlySessionDep, require_admin
from app.core.config import settings
from app.database.operations import table_select
from app.models.user import User
from app.schemas.status import StatusResponse

router = APIRouter(tags=["status"])


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Состояние сервера",
    dependencies=[Depends(require_admin)],
)
async def server_status(session: ReadonlySessionDep) -> StatusResponse:
    db_connected = False
    try:
        table_select(session, User, limit=1)
        db_connected = True
    except Exception:
        db_connected = False

    return StatusResponse(
        service=settings.app_name,
        status="running",
        debug=settings.debug,
        db_connected=db_connected,
    )
