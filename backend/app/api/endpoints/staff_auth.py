"""Endpoints аутентификации персонала (multi-tenant admin panel)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.config import settings
from app.core.dependencies import SessionDep, get_staff_principal
from app.domain.services.staff_auth_service import (
    authenticate_staff,
    staff_last_login_iso,
)
from app.infrastructure.persistence.models.staff_user import StaffUser

router = APIRouter(prefix="/staff/auth", tags=["staff"])


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class StaffProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    role: Literal["super_admin", "admin", "manager"]
    projects: list[int] | None = None
    last_login_at: str | None = None


class StaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: StaffProfileResponse


@router.post("/login", response_model=StaffLoginResponse, summary="Логин персонала (email + password)")
async def staff_login(body: StaffLoginRequest, session: SessionDep) -> StaffLoginResponse:
    token, staff, projects = await authenticate_staff(
        session,
        email=str(body.email),
        password=body.password,
        settings=settings,
    )
    return StaffLoginResponse(
        access_token=token,
        profile=StaffProfileResponse(
            id=int(staff.id),
            email=staff.email,
            full_name=staff.full_name,
            role=staff.role,  # type: ignore[arg-type]
            projects=projects,
            last_login_at=staff_last_login_iso(staff.last_login_at),
        ),
    )


@router.get("/me", response_model=StaffProfileResponse, summary="Текущий staff-пользователь")
async def staff_me(
    session: SessionDep,
    claims=Depends(get_staff_principal),
) -> StaffProfileResponse:
    from app.domain.services.staff_auth_service import _load_projects_for

    row = (
        await session.execute(select(StaffUser).where(StaffUser.id == claims.staff_user_id))
    ).scalars().first()
    if row is None:
        from app.core.exceptions import UnauthorizedError

        raise UnauthorizedError(detail="Staff-пользователь удалён")
    if row.role == "super_admin":
        projects: list[int] | None = None
    else:
        projects = await _load_projects_for(session, int(row.id))
    return StaffProfileResponse(
        id=int(row.id),
        email=row.email,
        full_name=row.full_name,
        role=row.role,  # type: ignore[arg-type]
        projects=projects,
        last_login_at=staff_last_login_iso(row.last_login_at),
    )
