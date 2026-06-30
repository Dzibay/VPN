"""Оркестрация API групп реферальных токенов."""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.domain.models.referral_link_groups import (
    ReferralLinkGroupCreate,
    ReferralLinkGroupMembersBody,
    ReferralLinkGroupRead,
    ReferralLinkGroupUpdate,
)
from app.domain.referrals.groups_repository import (
    add_referral_link_group_members,
    create_referral_link_group,
    delete_referral_link_group,
    list_referral_link_groups,
    remove_referral_link_group_member,
    set_referral_link_group_members,
    update_referral_link_group,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _group_to_read(row, link_ids: list[int]) -> ReferralLinkGroupRead:
    return ReferralLinkGroupRead(
        id=int(row.id),
        name=row.name,
        color=row.color,
        sort_order=int(row.sort_order),
        created_at=row.created_at,
        link_ids=link_ids,
    )


async def list_staff_referral_link_groups(session: AsyncSession) -> list[ReferralLinkGroupRead]:
    rows = await list_referral_link_groups(session)
    return [_group_to_read(row, link_ids) for row, link_ids in rows]


async def create_staff_referral_link_group(
    session: AsyncSession,
    body: ReferralLinkGroupCreate,
) -> ReferralLinkGroupRead:
    row, link_ids = await create_referral_link_group(
        session,
        name=body.name,
        color=body.color,
        link_ids=body.link_ids,
        sort_order=body.sort_order,
    )
    return _group_to_read(row, link_ids)


async def patch_staff_referral_link_group(
    session: AsyncSession,
    group_id: int,
    body: ReferralLinkGroupUpdate,
) -> ReferralLinkGroupRead:
    body.at_least_one_field()
    row = await update_referral_link_group(
        session,
        group_id,
        name=body.name,
        color=body.color,
        sort_order=body.sort_order,
    )
    from app.domain.referrals.groups_repository import _link_ids_for_group

    link_ids = await _link_ids_for_group(session, group_id)
    return _group_to_read(row, link_ids)


async def replace_staff_referral_link_group_members(
    session: AsyncSession,
    group_id: int,
    body: ReferralLinkGroupMembersBody,
) -> ReferralLinkGroupRead:
    from app.domain.referrals.groups_repository import (
        _link_ids_for_group,
        get_referral_link_group_row,
    )

    row = await get_referral_link_group_row(session, group_id)
    link_ids = await set_referral_link_group_members(session, group_id, body.link_ids)
    return _group_to_read(row, link_ids)


async def add_staff_referral_link_group_members(
    session: AsyncSession,
    group_id: int,
    body: ReferralLinkGroupMembersBody,
) -> ReferralLinkGroupRead:
    from app.domain.referrals.groups_repository import (
        _link_ids_for_group,
        get_referral_link_group_row,
    )

    row = await get_referral_link_group_row(session, group_id)
    link_ids = await add_referral_link_group_members(session, group_id, body.link_ids)
    return _group_to_read(row, link_ids)


async def remove_staff_referral_link_group_member(
    session: AsyncSession,
    group_id: int,
    link_id: int,
) -> ReferralLinkGroupRead:
    from app.domain.referrals.groups_repository import get_referral_link_group_row

    row = await get_referral_link_group_row(session, group_id)
    link_ids = await remove_referral_link_group_member(session, group_id, link_id)
    return _group_to_read(row, link_ids)


async def delete_staff_referral_link_group(session: AsyncSession, group_id: int) -> None:
    if not await delete_referral_link_group(session, group_id):
        raise NotFoundError("Группа не найдена")
