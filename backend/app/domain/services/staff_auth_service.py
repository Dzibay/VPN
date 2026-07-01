"""Аутентификация персонала: логин email/password → staff-JWT со списком проектов."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.passwords import verify_password
from app.core.staff_token import StaffRole, create_staff_token
from app.core.time import utc_now
from app.infrastructure.persistence.models.staff_user import StaffUser
from app.infrastructure.persistence.models.staff_user_project_access import (
    StaffUserProjectAccess,
)


async def _load_staff_by_email(session: AsyncSession, email: str) -> StaffUser | None:
    row = (
        await session.execute(select(StaffUser).where(StaffUser.email == email))
    ).scalars().first()
    return row


async def _load_projects_for(session: AsyncSession, staff_user_id: int) -> list[int]:
    rows = (
        await session.execute(
            select(StaffUserProjectAccess.project_id).where(
                StaffUserProjectAccess.staff_user_id == staff_user_id
            )
        )
    ).all()
    return [int(r[0]) for r in rows]


async def authenticate_staff(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings,
) -> tuple[str, StaffUser, list[int] | None]:
    """Возвращает (access_token, staff_row, projects_list_or_none)."""
    email_norm = (email or "").strip().lower()
    if not email_norm or not password:
        raise UnauthorizedError(detail="Неверный логин или пароль")

    staff = await _load_staff_by_email(session, email_norm)
    if staff is None or not staff.is_active:
        raise UnauthorizedError(detail="Неверный логин или пароль")

    if not verify_password(password, staff.password_hash):
        raise UnauthorizedError(detail="Неверный логин или пароль")

    role: StaffRole = staff.role  # type: ignore[assignment]
    projects: list[int] | None
    if role == "super_admin":
        projects = None
    else:
        projects = await _load_projects_for(session, int(staff.id))

    await session.execute(
        update(StaffUser)
        .where(StaffUser.id == staff.id)
        .values(last_login_at=utc_now())
    )
    await session.commit()

    token = create_staff_token(
        settings,
        staff_user_id=int(staff.id),
        role=role,
        projects=projects,
    )
    return token, staff, projects


def staff_last_login_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
