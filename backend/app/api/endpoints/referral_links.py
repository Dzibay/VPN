"""Админка: реферальные токены и счётчики конверсии."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import select

from app.api.deps import ReadonlySessionDep, SessionDep, require_referrals_staff
from app.core.config import settings
from app.models.referral_link import ReferralLink
from app.schemas.referral_links import ReferralLinkCreate, ReferralLinkOut, ReferralLinkUpdate
from app.services.referral_link_service import create_referral_link, referral_link_to_out, update_referral_link

log = logging.getLogger("app.referral_links")

router = APIRouter(
    prefix="/referral-links",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@router.get(
    "",
    response_model=list[ReferralLinkOut],
    summary="Список реферальных токенов",
)
async def list_referral_links(session: ReadonlySessionDep) -> list[ReferralLinkOut]:
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list(session.scalars(stmt).all())
    return [referral_link_to_out(r, settings) for r in rows]


@router.post(
    "",
    response_model=ReferralLinkOut,
    status_code=201,
    summary="Создать реферальный токен",
)
async def post_referral_link(
    body: ReferralLinkCreate,
    session: SessionDep,
) -> ReferralLinkOut:
    try:
        row = create_referral_link(
            session,
            owner_kind=body.owner_kind,
            owner_user_id=body.owner_user_id,
            token=body.token,
        )
        return referral_link_to_out(row, settings)
    except ValueError as e:
        detail = str(e)
        status = 409 if "уже занят" in detail else 422
        raise HTTPException(status_code=status, detail=detail) from e


@router.patch(
    "/{link_id}",
    response_model=ReferralLinkOut,
    summary="Изменить реферальный токен и источник",
)
async def patch_referral_link(
    body: ReferralLinkUpdate,
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="id в таблице referral_links")],
) -> ReferralLinkOut:
    try:
        row = update_referral_link(
            session,
            link_id,
            owner_kind=body.owner_kind,
            owner_user_id=body.owner_user_id,
            token=body.token,
        )
        return referral_link_to_out(row, settings)
    except ValueError as e:
        detail = str(e)
        if detail == "Запись не найдена":
            raise HTTPException(status_code=404, detail=detail) from e
        status = 409 if "уже занят" in detail else 422
        raise HTTPException(status_code=status, detail=detail) from e


@router.delete(
    "/{link_id}",
    status_code=204,
    summary="Удалить реферальный токен",
)
async def delete_referral_link(
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="id в таблице referral_links")],
) -> Response:
    stmt = select(ReferralLink).where(ReferralLink.id == link_id).limit(1)
    row = session.scalars(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Токен не найден")
    session.delete(row)
    return Response(status_code=204)
