"""Админка: реферальные токены и счётчики конверсии."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func, select

from app.api.deps import ReadonlySessionDep, SessionDep, require_referrals_staff
from app.core.config import settings
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.models.referral_link import ReferralLink
from app.models.user import User
from app.schemas.referral_links import (
    ReferralFunnelSummary,
    ReferralLinkCreate,
    ReferralLinkOut,
    ReferralLinkUpdate,
)
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
    summary="Перечень реферальных ссылок",
)
async def list_referral_links(session: ReadonlySessionDep) -> list[ReferralLinkOut]:
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list(session.scalars(stmt).all())
    return [referral_link_to_out(r, settings) for r in rows]


@router.get(
    "/funnel",
    response_model=ReferralFunnelSummary,
    summary=(
        "Сводные показатели воронки: пользователи и потребление трафика; "
        "при указании referral_link_id — также счётчик кликов по ссылке"
    ),
)
async def referral_funnel_summary(
    session: ReadonlySessionDep,
    referral_link_id: Annotated[
        int | None,
        Query(
            ge=1,
            description="Идентификатор реферальной ссылки в базе; без параметра — агрегат по всем пользователям",
        ),
    ] = None,
) -> ReferralFunnelSummary:
    def _nz(v: object) -> int:
        try:
            n = int(v or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, n)

    latest = user_server_traffic_latest_subquery()
    per_user_traffic = (
        select(
            latest.c.user_id.label("uid"),
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            ).label("tot"),
        )
        .group_by(latest.c.user_id)
        .having(
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            )
            > 0,
        )
        .subquery()
    )

    if referral_link_id is not None:
        row = session.scalars(
            select(ReferralLink).where(ReferralLink.id == referral_link_id).limit(1),
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Реферальная ссылка не найдена")
        registrations_total_raw = row.registrations_count
        users_with_traffic_raw = session.scalar(
            select(func.count())
            .select_from(per_user_traffic)
            .join(User, User.id == per_user_traffic.c.uid)
            .where(User.referral_link_id == referral_link_id),
        )
        return ReferralFunnelSummary(
            clicks_total=_nz(row.clicks_count),
            registrations_total=_nz(registrations_total_raw),
            users_with_traffic=_nz(users_with_traffic_raw),
        )

    registrations_total_raw = session.scalar(select(func.count()).select_from(User))
    users_with_traffic_raw = session.scalar(select(func.count()).select_from(per_user_traffic))

    return ReferralFunnelSummary(
        clicks_total=None,
        registrations_total=_nz(registrations_total_raw),
        users_with_traffic=_nz(users_with_traffic_raw),
    )


@router.post(
    "",
    response_model=ReferralLinkOut,
    status_code=201,
    summary="Создание реферальной ссылки",
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
        status = (
            409
            if "уже занят" in detail or "уже есть персональная" in detail or "уже создана" in detail
            else 422
        )
        raise HTTPException(status_code=status, detail=detail) from e


@router.patch(
    "/{link_id}",
    response_model=ReferralLinkOut,
    summary="Частичное обновление реферальной ссылки",
)
async def patch_referral_link(
    body: ReferralLinkUpdate,
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="Первичный ключ referral_links.id")],
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
        status = (
            409
            if "уже занят" in detail or "уже есть персональная" in detail or "уже создана" in detail
            else 422
        )
        raise HTTPException(status_code=status, detail=detail) from e


@router.delete(
    "/{link_id}",
    status_code=204,
    summary="Удаление реферальной ссылки",
)
async def delete_referral_link(
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="Первичный ключ referral_links.id")],
) -> Response:
    stmt = select(ReferralLink).where(ReferralLink.id == link_id).limit(1)
    row = session.scalars(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Токен не найден")
    session.delete(row)
    return Response(status_code=204)
