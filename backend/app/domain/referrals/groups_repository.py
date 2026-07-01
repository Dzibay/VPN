"""CRUD групп реферальных токенов и назначение membership."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.referral_link_groups import DEFAULT_GROUP_COLOR
from app.domain.referrals.errors import ReferralLinkGroupNotFoundError
from app.domain.tenant.admin_project_scope import admin_project_id, apply_project_scope
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.referral_link_group import ReferralLinkGroup


async def list_referral_link_groups(session: AsyncSession) -> list[tuple[ReferralLinkGroup, list[int]]]:
    groups = list(
        (
            await session.scalars(
                apply_project_scope(
                    select(ReferralLinkGroup).order_by(
                        ReferralLinkGroup.sort_order.asc(),
                        ReferralLinkGroup.id.asc(),
                    ),
                    ReferralLinkGroup,
                ),
            )
        ).all(),
    )
    if not groups:
        return []

    group_ids = [int(g.id) for g in groups]
    link_rows = (
        await session.execute(
            select(ReferralLink.id, ReferralLink.group_id)
            .where(ReferralLink.group_id.in_(group_ids))
            .order_by(ReferralLink.id.asc()),
        )
    ).all()
    by_group: dict[int, list[int]] = {gid: [] for gid in group_ids}
    for link_id, group_id in link_rows:
        if group_id is not None:
            by_group[int(group_id)].append(int(link_id))
    return [(g, by_group[int(g.id)]) for g in groups]


async def get_referral_link_group_row(session: AsyncSession, group_id: int) -> ReferralLinkGroup:
    row = await session.get(ReferralLinkGroup, group_id)
    if row is None:
        raise ReferralLinkGroupNotFoundError
    pid = admin_project_id()
    if pid is not None and int(row.project_id) != pid:
        raise ReferralLinkGroupNotFoundError
    return row


async def _link_ids_for_group(session: AsyncSession, group_id: int) -> list[int]:
    rows = (
        await session.scalars(
            select(ReferralLink.id)
            .where(ReferralLink.group_id == group_id)
            .order_by(ReferralLink.id.asc()),
        )
    ).all()
    return [int(x) for x in rows]


async def create_referral_link_group(
    session: AsyncSession,
    *,
    name: str,
    color: str | None,
    link_ids: list[int],
    sort_order: int | None,
) -> tuple[ReferralLinkGroup, list[int]]:
    next_order = sort_order
    if next_order is None:
        max_order = await session.scalar(select(func.max(ReferralLinkGroup.sort_order)))
        next_order = int(max_order or 0) + 1

    row = ReferralLinkGroup(
        name=name.strip(),
        color=(color or DEFAULT_GROUP_COLOR).lower(),
        sort_order=int(next_order),
    )
    session.add(row)
    await session.flush()
    await set_referral_link_group_members(session, int(row.id), link_ids)
    return row, await _link_ids_for_group(session, int(row.id))


async def update_referral_link_group(
    session: AsyncSession,
    group_id: int,
    *,
    name: str | None,
    color: str | None,
    sort_order: int | None,
) -> ReferralLinkGroup:
    row = await get_referral_link_group_row(session, group_id)
    if name is not None:
        row.name = name.strip()
    if color is not None:
        row.color = color.lower()
    if sort_order is not None:
        row.sort_order = int(sort_order)
    await session.flush()
    return row


async def set_referral_link_group_members(
    session: AsyncSession,
    group_id: int,
    link_ids: list[int],
) -> list[int]:
    await get_referral_link_group_row(session, group_id)
    await session.execute(
        update(ReferralLink)
        .where(ReferralLink.group_id == group_id, ReferralLink.id.not_in(link_ids or [-1]))
        .values(group_id=None),
    )
    if link_ids:
        await session.execute(
            update(ReferralLink).where(ReferralLink.id.in_(link_ids)).values(group_id=group_id),
        )
    await session.flush()
    return await _link_ids_for_group(session, group_id)


async def add_referral_link_group_members(
    session: AsyncSession,
    group_id: int,
    link_ids: list[int],
) -> list[int]:
    await get_referral_link_group_row(session, group_id)
    if not link_ids:
        return await _link_ids_for_group(session, group_id)
    await session.execute(
        update(ReferralLink).where(ReferralLink.id.in_(link_ids)).values(group_id=group_id),
    )
    await session.flush()
    return await _link_ids_for_group(session, group_id)


async def remove_referral_link_group_member(
    session: AsyncSession,
    group_id: int,
    link_id: int,
) -> list[int]:
    await get_referral_link_group_row(session, group_id)
    await session.execute(
        update(ReferralLink)
        .where(ReferralLink.id == link_id, ReferralLink.group_id == group_id)
        .values(group_id=None),
    )
    await session.flush()
    return await _link_ids_for_group(session, group_id)


async def delete_referral_link_group(session: AsyncSession, group_id: int) -> bool:
    row = await session.get(ReferralLinkGroup, group_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
