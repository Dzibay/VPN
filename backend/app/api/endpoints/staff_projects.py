"""Admin CRUD: projects, project_tariffs, staff_users.

Все endpoints требуют staff-JWT. Управление проектами/персоналом — super_admin only.
Управление тарифами — staff с доступом к конкретному проекту.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from app.core.dependencies import (
    SessionDep,
    get_staff_principal,
    require_super_admin,
)
from app.domain.services import projects_service as svc

router = APIRouter(prefix="/admin", tags=["staff-admin"])


# ---------- /admin/projects ----------


@router.get("/projects", dependencies=[Depends(get_staff_principal)])
async def admin_list_projects(session: SessionDep) -> list[dict[str, Any]]:
    return await svc.list_projects(session)


@router.get("/projects/{project_id}", dependencies=[Depends(get_staff_principal)])
async def admin_get_project(project_id: int, session: SessionDep) -> dict[str, Any]:
    return await svc.get_project(session, project_id)


@router.post("/projects", dependencies=[Depends(require_super_admin)])
async def admin_create_project(
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.create_project(session, body)


@router.patch("/projects/{project_id}", dependencies=[Depends(require_super_admin)])
async def admin_update_project(
    project_id: int,
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.update_project(session, project_id, body)


@router.delete("/projects/{project_id}", dependencies=[Depends(require_super_admin)])
async def admin_delete_project(
    project_id: int,
    session: SessionDep,
) -> dict[str, str]:
    await svc.delete_project(session, project_id)
    return {"status": "ok"}


# ---------- /admin/projects/{id}/tariffs ----------


@router.get(
    "/projects/{project_id}/tariffs",
    dependencies=[Depends(get_staff_principal)],
)
async def admin_list_project_tariffs(
    project_id: int, session: SessionDep
) -> list[dict[str, Any]]:
    return await svc.list_project_tariffs(session, project_id)


@router.post(
    "/projects/{project_id}/tariffs",
    dependencies=[Depends(require_super_admin)],
)
async def admin_create_project_tariff(
    project_id: int,
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.create_project_tariff(session, project_id, body)


@router.patch("/tariffs/{tariff_id}", dependencies=[Depends(require_super_admin)])
async def admin_update_project_tariff(
    tariff_id: int,
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.update_project_tariff(session, tariff_id, body)


@router.delete("/tariffs/{tariff_id}", dependencies=[Depends(require_super_admin)])
async def admin_delete_project_tariff(
    tariff_id: int, session: SessionDep
) -> dict[str, str]:
    await svc.delete_project_tariff(session, tariff_id)
    return {"status": "ok"}


# ---------- /admin/staff-users ----------


@router.get("/staff-users", dependencies=[Depends(require_super_admin)])
async def admin_list_staff_users(session: SessionDep) -> list[dict[str, Any]]:
    return await svc.list_staff_users(session)


@router.post("/staff-users", dependencies=[Depends(require_super_admin)])
async def admin_create_staff_user(
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.create_staff_user(session, body)


@router.patch("/staff-users/{staff_id}", dependencies=[Depends(require_super_admin)])
async def admin_update_staff_user(
    staff_id: int,
    session: SessionDep,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await svc.update_staff_user(session, staff_id, body)


@router.delete("/staff-users/{staff_id}", dependencies=[Depends(require_super_admin)])
async def admin_delete_staff_user(
    staff_id: int, session: SessionDep
) -> dict[str, str]:
    await svc.delete_staff_user(session, staff_id)
    return {"status": "ok"}
