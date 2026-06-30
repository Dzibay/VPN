"""Группы реферальных токенов (админка)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from app.core.dependencies import ReadonlySessionDep, SessionDep, require_referrals_staff
from app.domain.models.referral_link_groups import (
    ReferralLinkGroupCreate,
    ReferralLinkGroupMembersBody,
    ReferralLinkGroupRead,
    ReferralLinkGroupUpdate,
)
from app.domain.services.referral_link_groups_service import (
    add_staff_referral_link_group_members,
    create_staff_referral_link_group,
    delete_staff_referral_link_group,
    list_staff_referral_link_groups,
    patch_staff_referral_link_group,
    remove_staff_referral_link_group_member,
    replace_staff_referral_link_group_members,
)

router = APIRouter(
    prefix="/referral-link-groups",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "",
    response_model=list[ReferralLinkGroupRead],
    summary="Группы реферальных токенов",
)
async def list_referral_link_groups(session: ReadonlySessionDep) -> list[ReferralLinkGroupRead]:
    return await list_staff_referral_link_groups(session)


@router.post(
    "",
    response_model=ReferralLinkGroupRead,
    status_code=201,
    summary="Создание группы реферальных токенов",
)
async def post_referral_link_group(
    body: ReferralLinkGroupCreate,
    session: SessionDep,
) -> ReferralLinkGroupRead:
    return await create_staff_referral_link_group(session, body)


@router.patch(
    "/{group_id}",
    response_model=ReferralLinkGroupRead,
    summary="Обновление группы (название, цвет, порядок)",
)
async def patch_referral_link_group(
    body: ReferralLinkGroupUpdate,
    session: SessionDep,
    group_id: Annotated[int, Path(ge=1)],
) -> ReferralLinkGroupRead:
    return await patch_staff_referral_link_group(session, group_id, body)


@router.put(
    "/{group_id}/members",
    response_model=ReferralLinkGroupRead,
    summary="Задать полный состав группы",
)
async def put_referral_link_group_members(
    body: ReferralLinkGroupMembersBody,
    session: SessionDep,
    group_id: Annotated[int, Path(ge=1)],
) -> ReferralLinkGroupRead:
    return await replace_staff_referral_link_group_members(session, group_id, body)


@router.post(
    "/{group_id}/members",
    response_model=ReferralLinkGroupRead,
    summary="Добавить токены в группу",
)
async def post_referral_link_group_members(
    body: ReferralLinkGroupMembersBody,
    session: SessionDep,
    group_id: Annotated[int, Path(ge=1)],
) -> ReferralLinkGroupRead:
    return await add_staff_referral_link_group_members(session, group_id, body)


@router.delete(
    "/{group_id}/members/{link_id}",
    response_model=ReferralLinkGroupRead,
    summary="Убрать токен из группы",
)
async def delete_referral_link_group_member(
    session: SessionDep,
    group_id: Annotated[int, Path(ge=1)],
    link_id: Annotated[int, Path(ge=1)],
) -> ReferralLinkGroupRead:
    return await remove_staff_referral_link_group_member(session, group_id, link_id)


@router.delete(
    "/{group_id}",
    status_code=204,
    summary="Удаление группы (токены остаются без группы)",
)
async def delete_referral_link_group(
    session: SessionDep,
    group_id: Annotated[int, Path(ge=1)],
) -> Response:
    await delete_staff_referral_link_group(session, group_id)
    return Response(status_code=204)
