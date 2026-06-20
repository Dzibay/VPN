"""Реферальные ссылки: админка, публичный трекинг кликов, персональная ссылка пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.config import settings
from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_referral_links_api_key,
    require_referrals_staff,
)
from app.domain.models.referral_links import (
    ReferralExternalLinkCreateBody,
    ReferralFunnelSummary,
    ReferralLinkCreate,
    ReferralLinkOut,
    ReferralLinkUpdate,
    ReferralMeResponse,
    ReferralTrackClickBody,
    ReferralTokensRegistrationsDailySummary,
    ReferralTrafficOverviewStats,
)
from app.domain.referrals.funnel import referral_funnel_compute
from app.domain.referrals.public_links import referral_link_to_response
from app.domain.referrals.repository import (
    create_referral_link,
    get_or_create_external_referral_link,
    increment_referral_counter_by_token,
    update_referral_link,
)
from app.domain.services.referral_links_service import (
    delete_referral_link_row,
    get_staff_referral_link_by_id,
    list_staff_referral_links,
    referral_me_for_user,
    referral_me_user_id_from_bearer,
    referral_tokens_registrations_daily_summary,
    referral_traffic_overview_stats,
)

staff_router = APIRouter(
    prefix="/referral-links",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


@staff_router.get(
    "",
    response_model=list[ReferralLinkOut],
    summary="Перечень реферальных ссылок",
)
async def list_referral_links(session: ReadonlySessionDep) -> list[ReferralLinkOut]:
    return await list_staff_referral_links(session, settings)


@staff_router.get(
    "/traffic-stats",
    response_model=ReferralTrafficOverviewStats,
    summary=(
        "Сводка по источникам регистрации учётных пользователей "
        "(Telegram или подтверждённый email): прямой трафик, созданные ссылки, приглашения"
    ),
)
async def referral_traffic_stats(
    session: ReadonlySessionDep,
) -> ReferralTrafficOverviewStats:
    return await referral_traffic_overview_stats(session)


@staff_router.get(
    "/registrations-by-day",
    response_model=ReferralTokensRegistrationsDailySummary,
    summary=(
        "Регистрации по календарным дням Europe/Moscow для реферальных токенов "
        "с registrations_count выше порога"
    ),
)
async def referral_tokens_registrations_by_day(
    session: ReadonlySessionDep,
    response: Response,
    days: int = Query(
        30,
        ge=1,
        le=366,
        description="Глубина окна в календарных днях Europe/Moscow от сегодня включительно",
    ),
    min_registrations: int = Query(
        10,
        ge=0,
        le=1_000_000,
        description="Включать только токены с registrations_count строго больше этого значения",
    ),
) -> ReferralTokensRegistrationsDailySummary:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return await referral_tokens_registrations_daily_summary(
        session,
        days=days,
        min_registrations=min_registrations,
    )


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
    return await referral_funnel_compute(session, referral_link_id, settings)


@staff_router.get(
    "/{link_id}",
    response_model=ReferralLinkOut,
    summary="Одна реферальная ссылка по id",
)
async def get_referral_link(
    session: ReadonlySessionDep,
    link_id: Annotated[int, Path(ge=1, description="Первичный ключ referral_links.id")],
) -> ReferralLinkOut:
    return await get_staff_referral_link_by_id(session, link_id, settings)


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
    row = await create_referral_link(
        session,
        owner_kind=body.owner_kind,
        owner_user_id=body.owner_user_id,
        token=body.token,
    )
    return referral_link_to_response(row, settings)


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
    row = await update_referral_link(
        session,
        link_id,
        owner_kind=body.owner_kind,
        owner_user_id=body.owner_user_id,
        token=body.token,
    )
    return referral_link_to_response(row, settings)


@staff_router.delete(
    "/{link_id}",
    status_code=204,
    summary="Удаление реферальной ссылки",
)
async def delete_referral_link(
    session: SessionDep,
    link_id: Annotated[int, Path(ge=1, description="Первичный ключ referral_links.id")],
) -> Response:
    await delete_referral_link_row(session, link_id)
    return Response(status_code=204)


external_router = APIRouter(
    prefix="/referral/external",
    tags=["external"],
    dependencies=[Depends(require_referral_links_api_key)],
)


@external_router.post(
    "/links",
    response_model=ReferralLinkOut,
    summary="Создание или получение реферальной ссылки (внешние сервисы)",
    description=(
        "Идемпотентно: если ``token`` уже есть в базе — возвращается существующая ссылка, "
        "иначе создаётся запись с ``owner_kind=token``. "
        "Заголовок ``X-API-Key`` — значение ``REFERRAL_LINKS_API_KEY``."
    ),
    responses={
        200: {"description": "Ссылка уже существовала"},
        201: {"description": "Ссылка создана"},
    },
    openapi_extra={"security": [{"ReferralLinksApiKey": []}]},
)
async def post_external_referral_link(
    body: ReferralExternalLinkCreateBody,
    session: SessionDep,
    response: Response,
) -> ReferralLinkOut:
    row, created = await get_or_create_external_referral_link(session, body.token)
    response.status_code = 201 if created else 200
    return referral_link_to_response(row, settings)


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
    await increment_referral_counter_by_token(session, body.token, "clicks")
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
    uid = referral_me_user_id_from_bearer(principal)
    return await referral_me_for_user(session, uid, settings)
