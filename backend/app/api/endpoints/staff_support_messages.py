"""Чат поддержки — inbox staff (admin / manager)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_referrals_staff,
)
from app.domain.models.support_messages import (
    StaffSupportBadgeResponse,
    StaffSupportChatsListResponse,
    StaffSupportMessageRead,
    StaffSupportMessagesListResponse,
    SupportMessageCreate,
)
from app.domain.services.support_messages_service import (
    create_staff_support_message,
    list_staff_support_chats,
    list_user_support_messages_for_staff,
    staff_support_needs_reply_count,
)

router = APIRouter(
    prefix="/staff/support-chats",
    tags=["admin"],
    dependencies=[Depends(require_referrals_staff)],
)


def _include_staff_author(principal: BearerPrincipal) -> bool:
    return principal.role == "admin"


@router.get(
    "",
    response_model=StaffSupportChatsListResponse,
    summary="Список чатов поддержки",
)
async def staff_support_chats(
    session: ReadonlySessionDep,
    limit: int = Query(100, ge=1, le=200, description="Размер страницы"),
    offset: int = Query(0, ge=0, description="Смещение"),
    only_needs_reply: bool = Query(
        False,
        description="Только чаты, где последнее сообщение от пользователя",
    ),
) -> StaffSupportChatsListResponse:
    items, total, needs_reply_count = await list_staff_support_chats(
        session,
        limit=limit,
        offset=offset,
        only_needs_reply=only_needs_reply,
    )
    return StaffSupportChatsListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        needs_reply_count=needs_reply_count,
    )


@router.get(
    "/badge",
    response_model=StaffSupportBadgeResponse,
    summary="Счётчик чатов, ожидающих ответа (лёгкий polling для шапки)",
)
async def staff_support_chats_badge(
    session: ReadonlySessionDep,
) -> StaffSupportBadgeResponse:
    count = await staff_support_needs_reply_count(session)
    return StaffSupportBadgeResponse(needs_reply_count=count)


@router.get(
    "/{user_id}/messages",
    response_model=StaffSupportMessagesListResponse,
    summary="Сообщения чата с пользователем",
)
async def staff_support_chat_messages(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    user_id: Annotated[int, Path(ge=1, description="ID пользователя")],
    limit: int = Query(200, ge=1, le=500, description="Размер страницы"),
    offset: int = Query(0, ge=0, description="Смещение"),
) -> StaffSupportMessagesListResponse:
    items, total = await list_user_support_messages_for_staff(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
        include_staff_author=_include_staff_author(principal),
    )
    return StaffSupportMessagesListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{user_id}/messages",
    response_model=StaffSupportMessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ответить пользователю в чате поддержки",
)
async def staff_support_chat_reply(
    session: SessionDep,
    body: SupportMessageCreate,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
    user_id: Annotated[int, Path(ge=1, description="ID пользователя")],
) -> StaffSupportMessageRead:
    include_staff_author = _include_staff_author(principal)
    return await create_staff_support_message(
        session,
        user_id=user_id,
        body=body.body,
        staff_user_id=int(principal.user_id) if principal.user_id is not None else None,
        include_staff_author=include_staff_author,
    )
