from fastapi import APIRouter, HTTPException, Query, Response

from app.core.dependencies import jwt_gate_active
from app.domain.models.status import HealthResponse
from app.domain.tenant.project_cache import get_project_by_host

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


@router.get(
    "/tls/ask",
    include_in_schema=False,
    summary="Caddy on-demand TLS allowlist по доменам активных проектов",
)
async def caddy_tls_ask(domain: str = Query(..., min_length=1)) -> Response:
    project = await get_project_by_host(domain)
    if project is None:
        raise HTTPException(status_code=404, detail="domain is not allowed")
    return Response(status_code=204)
