"""Блокировка IP — только admin JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import ReadonlySessionDep, SessionDep, require_admin
from app.domain.models.blocked_ips import BlockedIpCreate, BlockedIpRead
from app.domain.services.blocked_ips_service import (
    create_blocked_ip,
    delete_blocked_ip,
    list_blocked_ips,
)

router = APIRouter(
    prefix="/admin/blocked-ips",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=list[BlockedIpRead],
    summary="Список заблокированных IP (только admin)",
)
async def list_blocked_ips_ep(
    session: ReadonlySessionDep,
    _: Annotated[None, Depends(require_admin)],
) -> list[BlockedIpRead]:
    return await list_blocked_ips(session)


@router.post(
    "",
    response_model=BlockedIpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить IP в блокировку (только admin)",
)
async def create_blocked_ip_ep(
    session: SessionDep,
    body: BlockedIpCreate,
    _: Annotated[None, Depends(require_admin)],
) -> BlockedIpRead:
    return await create_blocked_ip(session, body)


@router.delete(
    "/{blocked_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать IP из блокировки (только admin)",
)
async def delete_blocked_ip_ep(
    session: SessionDep,
    blocked_id: int,
    _: Annotated[None, Depends(require_admin)],
) -> None:
    await delete_blocked_ip(session, blocked_id)
