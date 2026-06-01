"""Поиск пользователей для админки (по email, telegram_id и username из telegram_properties)."""

from __future__ import annotations

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.users import StaffUserSearchItem
from app.infrastructure.persistence.models.user import User


def _escape_like_pattern(fragment: str) -> str:
    return (
        fragment.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


async def search_staff_users(
    session: AsyncSession,
    *,
    q: str,
    limit: int = 30,
) -> list[StaffUserSearchItem]:
    """Поиск по email, telegram_id (подстрока в тексте), telegram_properties.username (ILIKE)."""
    raw = q.strip()
    if len(raw) < 3:
        return []
    cap = min(max(1, limit), 50)
    pattern = f"%{_escape_like_pattern(raw)}%"
    username_ast = User.telegram_properties["username"].astext
    stmt = (
        select(User)
        .where(
            or_(
                User.email.ilike(pattern, escape="\\"),
                cast(User.telegram_id, String).ilike(pattern, escape="\\"),
                func.coalesce(username_ast, "").ilike(pattern, escape="\\"),
            ),
        )
        .order_by(User.id.desc())
        .limit(cap)
    )
    rows = list((await session.scalars(stmt)).all())
    out: list[StaffUserSearchItem] = []
    for u in rows:
        props = u.telegram_properties if isinstance(u.telegram_properties, dict) else None
        uname = props.get("username") if props else None
        if isinstance(uname, str):
            uname = uname.strip() or None
        else:
            uname = None
        out.append(
            StaffUserSearchItem(
                id=int(u.id),
                email=u.email,
                telegram_id=int(u.telegram_id) if u.telegram_id is not None else None,
                telegram_username=uname,
            ),
        )
    return out
