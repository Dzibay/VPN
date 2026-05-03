"""Реферальные ссылки: админка, публичный трекинг кликов, персональная ссылка пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.config import settings
from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_referrals_staff,
)
from app.domain.models.referral_links import (
    ReferralFunnelSummary,
    ReferralLinkCreate,
    ReferralLinkOut,
    ReferralLinkUpdate,
    ReferralMeResponse,
    ReferralTrackClickBody,
)
from app.domain.services.http_errors import HttpServiceError
from app.domain.services.referral_links_service import (
    client_site_user_id,
    create_referral_link,
    delete_referral_link_row,
    increment_referral_counter_by_token,
    list_staff_referral_links,
    referral_funnel_compute,
    referral_link_to_out,
    referral_me_for_user,
    update_referral_link,
)

staff_router = APIRouter(
    prefix="/referral-links",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


def _raise_svc(e: HttpServiceError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@staff_router.get(
    "",
    response_model=list[ReferralLinkOut],
    summary="Перечень реферальных ссылок",
)
async def list_referral_links(session: ReadonlySessionDep) -> list[ReferralLinkOut]:
    return list_staff_referral_links(session, settings)


@staff_router.get(
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
    try:
        return referral_funnel_compute(session, referral_link_id, settings)
    except HttpServiceError as e:
        _raise_svc(e)


@staff_router.post(
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


@staff_router.patch(
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


@staff_router.delete(
    "/{link_id}",
    status_code=204,
    summary="Удаление реферальной ссылки",
)
async def delete_referral_link(
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="Первичный ключ referral_links.id")],
) -> Response:
    try:
        delete_referral_link_row(session, link_id)
    except HttpServiceError as e:
        _raise_svc(e)
    return Response(status_code=204)


public_router = APIRouter(prefix="/referral", tags=["public"])


@public_router.post(
    "/track-click",
    status_code=204,
    summary="Регистрация перехода по реферальной ссылке на сайте (инкремент счётчика кликов)",
)
async def track_referral_click(
    body: ReferralTrackClickBody,
    session: SessionDep,
) -> Response:
    increment_referral_counter_by_token(session, body.token, "clicks")
    return Response(status_code=204)


me_router = APIRouter(prefix="/referral/me", tags=["user"])


@me_router.get(
    "",
    response_model=ReferralMeResponse,
    summary="Персональная реферальная ссылка текущего пользователя",
    description=(
        "Возвращает существующую персональную ссылку или создаёт её при первом обращении "
        "(не более одной на учётную запись)."
    ),
)
async def get_my_referral_link(
    session: SessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> ReferralMeResponse:
    try:
        uid = client_site_user_id(principal)
        return referral_me_for_user(session, uid, settings)
    except HttpServiceError as e:
        _raise_svc(e)
