"""Чат поддержки: сообщения пользователя и ответы staff."""

from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.time import utc_now
from app.domain.models.support_messages import (
    StaffSupportChatSummary,
    StaffSupportMessageRead,
    SupportMessageRead,
)
from app.domain.tenant.admin_project_scope import admin_project_id, project_scope_clause
from app.infrastructure.persistence.models.support_message import SupportMessage
from app.infrastructure.persistence.models.user import User

_PREVIEW_LEN = 160


def _telegram_username(user: User) -> str | None:
    props = user.telegram_properties if isinstance(user.telegram_properties, dict) else None
    if not props:
        return None
    uname = props.get("username")
    if not isinstance(uname, str):
        return None
    trimmed = uname.strip().lstrip("@")
    return trimmed or None


def _user_display_label(user: User) -> str:
    if user.email and str(user.email).strip():
        return str(user.email).strip()
    uname = _telegram_username(user)
    if uname:
        return f"@{uname}"
    if user.telegram_id is not None:
        return f"Telegram {user.telegram_id}"
    return f"Пользователь #{user.id}"


def _staff_author_label(user: User) -> str:
    role = str(user.account_role or "").strip().lower()
    prefix = "Админ" if role == "admin" else "Менеджер" if role == "manager" else "Staff"
    detail = _user_display_label(user)
    return f"{prefix}: {detail}"


def _preview_body(body: str) -> str:
    text = body.strip()
    if len(text) <= _PREVIEW_LEN:
        return text
    return f"{text[: _PREVIEW_LEN - 1].rstrip()}…"


def _to_staff_message_read(
    msg: SupportMessage,
    *,
    staff_users: dict[int, User],
    include_staff_author: bool,
) -> StaffSupportMessageRead:
    staff_author_label = None
    if (
        include_staff_author
        and msg.author_kind == "staff"
        and msg.staff_user_id is not None
    ):
        staff = staff_users.get(int(msg.staff_user_id))
        if staff is not None:
            staff_author_label = _staff_author_label(staff)
        else:
            staff_author_label = f"Staff #{msg.staff_user_id}"
    return StaffSupportMessageRead(
        id=int(msg.id),
        author_kind=msg.author_kind,  # type: ignore[arg-type]
        body=msg.body,
        created_at=msg.created_at,
        staff_user_id=int(msg.staff_user_id) if msg.staff_user_id is not None else None,
        staff_author_label=staff_author_label,
    )


async def _load_staff_users(
    session: AsyncSession,
    messages: list[SupportMessage],
) -> dict[int, User]:
    staff_ids = {
        int(msg.staff_user_id)
        for msg in messages
        if msg.author_kind == "staff" and msg.staff_user_id is not None
    }
    if not staff_ids:
        return {}
    stmt = select(User).where(User.id.in_(staff_ids))
    rows = list((await session.scalars(stmt)).all())
    return {int(u.id): u for u in rows}


async def list_my_support_messages(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[SupportMessageRead], int]:
    count_stmt = (
        select(func.count())
        .select_from(SupportMessage)
        .where(SupportMessage.user_id == user_id)
    )
    stmt = (
        select(SupportMessage)
        .where(SupportMessage.user_id == user_id)
        .order_by(SupportMessage.created_at.asc(), SupportMessage.id.asc())
        .limit(limit)
        .offset(offset)
    )
    total = int(await session.scalar(count_stmt) or 0)
    rows = list((await session.scalars(stmt)).all())
    return [SupportMessageRead.model_validate(r) for r in rows], total


async def create_user_support_message(
    session: AsyncSession,
    *,
    user_id: int,
    body: str,
) -> SupportMessageRead:
    row = SupportMessage(
        user_id=user_id,
        author_kind="user",
        body=body.strip(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return SupportMessageRead.model_validate(row)


async def count_unread_support_for_user(
    session: AsyncSession,
    *,
    user_id: int,
) -> int:
    """Ответы staff после support_seen_at (один запрос)."""
    uid = int(user_id)
    unread_filter = or_(
        User.support_seen_at.is_(None),
        SupportMessage.created_at > User.support_seen_at,
    )
    row = (
        await session.execute(
            select(func.count(SupportMessage.id))
            .select_from(User)
            .outerjoin(
                SupportMessage,
                (SupportMessage.user_id == User.id)
                & (SupportMessage.author_kind == "staff")
                & unread_filter,
            )
            .where(User.id == uid)
            .group_by(User.id),
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Пользователь не найден")
    return int(row[0] or 0)


async def mark_support_seen_for_user(
    session: AsyncSession,
    *,
    user_id: int,
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    user.support_seen_at = utc_now()


async def staff_support_needs_reply_count(session: AsyncSession) -> int:
    """Число чатов, где последнее сообщение от пользователя (один запрос, для бейджа в шапке)."""
    latest_q = (
        select(
            SupportMessage.user_id,
            SupportMessage.author_kind,
        )
        .distinct(SupportMessage.user_id)
        .order_by(SupportMessage.user_id, SupportMessage.id.desc())
    )
    scope = project_scope_clause(SupportMessage)
    if scope is not None:
        latest_q = latest_q.where(scope)
    latest_per_user = latest_q.subquery()
    stmt = (
        select(func.count())
        .select_from(latest_per_user)
        .where(latest_per_user.c.author_kind == "user")
    )
    return int(await session.scalar(stmt) or 0)


async def list_staff_support_chats(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    only_needs_reply: bool = False,
) -> tuple[list[StaffSupportChatSummary], int, int]:
    msg_scope = project_scope_clause(SupportMessage)
    latest_base = select(
        SupportMessage.user_id.label("user_id"),
        func.max(SupportMessage.id).label("last_message_id"),
        func.count().label("messages_count"),
    ).group_by(SupportMessage.user_id)
    if msg_scope is not None:
        latest_base = latest_base.where(msg_scope)
    latest_subq = latest_base.subquery()

    base_stmt = (
        select(
            SupportMessage,
            User,
            latest_subq.c.messages_count,
        )
        .join(latest_subq, SupportMessage.id == latest_subq.c.last_message_id)
        .join(User, User.id == SupportMessage.user_id)
    )
    if only_needs_reply:
        base_stmt = base_stmt.where(SupportMessage.author_kind == "user")

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = int(await session.scalar(count_stmt) or 0)

    needs_reply_count = await staff_support_needs_reply_count(session)

    stmt = base_stmt.order_by(
        case((SupportMessage.author_kind == "user", 0), else_=1),
        SupportMessage.created_at.desc(),
        SupportMessage.id.desc(),
    ).limit(limit).offset(offset)

    rows = list((await session.execute(stmt)).all())
    items: list[StaffSupportChatSummary] = []
    for msg, user, messages_count in rows:
        uname = _telegram_username(user)
        items.append(
            StaffSupportChatSummary(
                user_id=int(user.id),
                user_label=_user_display_label(user),
                user_email=user.email,
                telegram_username=uname,
                last_message_id=int(msg.id),
                last_message_body=_preview_body(msg.body),
                last_message_at=msg.created_at,
                last_author_kind=msg.author_kind,  # type: ignore[arg-type]
                needs_reply=msg.author_kind == "user",
                messages_count=int(messages_count or 0),
            ),
        )
    return items, total, needs_reply_count


async def list_user_support_messages_for_staff(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
    include_staff_author: bool = False,
) -> tuple[list[StaffSupportMessageRead], int]:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    pid = admin_project_id()
    if pid is not None and int(user.project_id) != pid:
        raise NotFoundError("Пользователь не найден")

    count_stmt = (
        select(func.count())
        .select_from(SupportMessage)
        .where(SupportMessage.user_id == user_id)
    )
    scope = project_scope_clause(SupportMessage)
    if scope is not None:
        count_stmt = count_stmt.where(scope)
    stmt = (
        select(SupportMessage)
        .where(SupportMessage.user_id == user_id)
        .order_by(SupportMessage.created_at.asc(), SupportMessage.id.asc())
        .limit(limit)
        .offset(offset)
    )
    if scope is not None:
        stmt = stmt.where(scope)
    total = int(await session.scalar(count_stmt) or 0)
    rows = list((await session.scalars(stmt)).all())
    staff_users = (
        await _load_staff_users(session, rows) if include_staff_author else {}
    )
    items = [
        _to_staff_message_read(
            msg,
            staff_users=staff_users,
            include_staff_author=include_staff_author,
        )
        for msg in rows
    ]
    return items, total


async def create_staff_support_message(
    session: AsyncSession,
    *,
    user_id: int,
    body: str,
    staff_user_id: int | None,
    include_staff_author: bool = False,
) -> StaffSupportMessageRead:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    row = SupportMessage(
        user_id=user_id,
        author_kind="staff",
        body=body.strip(),
        staff_user_id=staff_user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    staff_users: dict[int, User] = {}
    if include_staff_author and staff_user_id is not None:
        staff = await session.get(User, staff_user_id)
        if staff is not None:
            staff_users[int(staff.id)] = staff
    return _to_staff_message_read(
        row,
        staff_users=staff_users,
        include_staff_author=include_staff_author,
    )
