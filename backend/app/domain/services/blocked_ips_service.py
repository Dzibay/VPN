from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.domain.models.blocked_ips import BlockedIpCreate, BlockedIpRead
from app.domain.security.blocked_ip_cache import invalidate_blocked_ips_cache
from app.infrastructure.persistence.models.blocked_ip import BlockedIp


async def list_blocked_ips(session: AsyncSession) -> list[BlockedIpRead]:
    stmt = select(BlockedIp).order_by(BlockedIp.created_at.desc())
    rows = (await session.scalars(stmt)).all()
    return [BlockedIpRead.model_validate(r) for r in rows]


async def create_blocked_ip(session: AsyncSession, body: BlockedIpCreate) -> BlockedIpRead:
    row = BlockedIp(ip=body.ip, note=body.note)
    session.add(row)
    try:
        await session.flush()
        await session.refresh(row)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise BadRequestError("Этот IP уже в списке блокировки") from exc
    invalidate_blocked_ips_cache()
    return BlockedIpRead.model_validate(row)


async def delete_blocked_ip(session: AsyncSession, blocked_id: int) -> None:
    stmt = delete(BlockedIp).where(BlockedIp.id == blocked_id)
    res = await session.execute(stmt)
    if res.rowcount == 0:
        raise NotFoundError("Запись не найдена")
    await session.commit()
    invalidate_blocked_ips_cache()
