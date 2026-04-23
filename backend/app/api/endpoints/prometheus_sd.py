"""
HTTP service discovery для Prometheus (node_exporter).

Формат ответа: https://prometheus.io/docs/prometheus/latest/http_sd/
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select

from app.api.deps import ReadonlySessionDep
from app.core.config import settings
from app.core.http_bearer import bearer_token_or_none
from app.models.server import Server

router = APIRouter(prefix="/prometheus/sd", tags=["prometheus-sd"])


def _require_sd_bearer(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = (settings.prometheus_sd_token or "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    got = bearer_token_or_none(authorization)
    if got is None or not secrets.compare_digest(got, expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/node-exporter",
    dependencies=[Depends(_require_sd_bearer)],
    summary="Список целей node_exporter для Prometheus http_sd",
)
async def prometheus_sd_node_exporter(session: ReadonlySessionDep) -> list[dict[str, Any]]:
    """
    Активные серверы из БД → targets для scrape (host:port как в PromQL).
    """
    stmt = select(Server).where(Server.is_active.is_(True)).order_by(Server.id)
    servers = list(session.scalars(stmt).all())
    port = int(settings.provision_node_exporter_port)
    out: list[dict[str, Any]] = []
    for s in servers:
        inst = (s.prometheus_instance or "").strip()
        if not inst:
            inst = f"{s.host.strip()}:{port}"
        name = (s.name or "").strip()
        labels: dict[str, str] = {"server_id": str(s.id)}
        if name:
            labels["server_name"] = name
        out.append({"targets": [inst], "labels": labels})
    return out
