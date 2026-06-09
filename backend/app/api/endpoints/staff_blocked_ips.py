"""Список заблокированных IP — только admin JWT."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.dependencies import ReadonlySessionDep, SessionDep, require_admin
from app.domain.models.blocked_ips import BlockedIpCreate, BlockedIpRead
from app.domain.services.blocked_ips_service import (
    create_blocked_ip,
    delete_blocked_ip,
    list_blocked_ips,
)

router = APIRouter(
    prefix="/staff/blocked-ips",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=list[BlockedIpRead],
    summary="Список заблокированных IP",
)
async def list_blocked_ips_ep(session: ReadonlySessionDep) -> list[BlockedIpRead]:
    return await list_blocked_ips(session)


@router.post(
    "",
    response_model=BlockedIpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить IP в блокировку",
)
async def create_blocked_ip_ep(
    session: SessionDep,
    body: BlockedIpCreate,
) -> BlockedIpRead:
    return await create_blocked_ip(session, body)


@router.delete(
    "/{blocked_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать IP из блокировки",
)
async def delete_blocked_ip_ep(session: SessionDep, blocked_id: int) -> None:
    await delete_blocked_ip(session, blocked_id)
