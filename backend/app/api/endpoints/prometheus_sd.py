"""HTTP service discovery для Prometheus (node_exporter).

Формат ответа: https://prometheus.io/docs/prometheus/latest/http_sd/
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.security_bearer import bearer_jwt
from app.config import settings
from app.domain.services import prometheus_sd_service
from app.domain.services.prometheus_sd_cache import (
    read_node_exporter_targets_cache,
    write_node_exporter_targets_cache,
)
from app.infrastructure.database.session import AsyncSessionLocal

router = APIRouter(prefix="/prometheus/sd", tags=["admin"])


def _require_sd_bearer(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_jwt)],
) -> None:
    expected = (settings.prometheus_sd_token or "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    got = (creds.credentials.strip() if creds and creds.credentials else None) or None
    if got is None or not secrets.compare_digest(got, expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/node-exporter",
    dependencies=[Depends(_require_sd_bearer)],
    summary="HTTP service discovery Prometheus: цели scrape node_exporter",
)
async def prometheus_sd_node_exporter():
    """
    Активные серверы из БД → targets для scrape (host:port как в PromQL).
    Ответ из Redis-кэша (обновляется scheduler), без сессии БД на cache hit.
    """
    cached = read_node_exporter_targets_cache(settings)
    if cached is not None:
        return cached
    async with AsyncSessionLocal() as session:
        targets = await prometheus_sd_service.node_exporter_targets(session, settings)
    write_node_exporter_targets_cache(targets, cfg=settings)
    return targets
