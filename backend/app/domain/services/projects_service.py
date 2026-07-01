"""CRUD проектов и persona-заготовок для админ-API (super_admin only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.passwords import hash_password
from app.domain.tenant.project_cache import invalidate as invalidate_project_cache
from app.infrastructure.persistence.models.project import Project
from app.infrastructure.persistence.models.project_tariff import ProjectTariff
from app.infrastructure.persistence.models.staff_user import StaffUser
from app.infrastructure.persistence.models.staff_user_project_access import (
    StaffUserProjectAccess,
)

_PROJECT_MUTABLE_FIELDS = {
    "slug",
    "name",
    "is_active",
    "primary_domain",
    "extra_domains",
    "telegram_bot_username",
    "telegram_bot_api_secret",
    "support_telegram_username",
    "support_email",
    "tribute_api_key",
    "yookassa_shop_id",
    "yookassa_secret_key",
    "yookassa_return_url",
    "smtp_settings",
    "referral_bonus_days_per_paid_month",
    "referral_fixed_first_payment_bonus_rub",
    "referral_bonus_policy",
    "trial_days_after_registration",
    "trial_extra_days_referral_registration",
    "trial_traffic_limit_gib",
    "trial_traffic_limit_enabled",
    "happ_provider_id",
    "subscription_sub_expire_banner",
    "subscription_sub_info_banner",
    "brand",
}


def _serialize_project(row: Project, *, include_secrets: bool = True) -> dict[str, Any]:
    """Полная сериализация Project. include_secrets=False — маскирует api-ключи (для list-view)."""

    def _mask(v: str | None) -> str | None:
        if not v:
            return v
        if include_secrets:
            return v
        return "***" + v[-4:] if len(v) > 4 else "***"

    return {
        "id": int(row.id),
        "slug": row.slug,
        "name": row.name,
        "is_active": bool(row.is_active),
        "primary_domain": row.primary_domain,
        "extra_domains": list(row.extra_domains or []),
        "telegram_bot_username": row.telegram_bot_username,
        "telegram_bot_api_secret": _mask(row.telegram_bot_api_secret),
        "support_telegram_username": row.support_telegram_username,
        "support_email": row.support_email,
        "tribute_api_key": _mask(row.tribute_api_key),
        "yookassa_shop_id": row.yookassa_shop_id,
        "yookassa_secret_key": _mask(row.yookassa_secret_key),
        "yookassa_return_url": row.yookassa_return_url,
        "smtp_settings": row.smtp_settings,
        "referral_bonus_days_per_paid_month": row.referral_bonus_days_per_paid_month,
        "referral_fixed_first_payment_bonus_rub": row.referral_fixed_first_payment_bonus_rub,
        "referral_bonus_policy": row.referral_bonus_policy,
        "trial_days_after_registration": row.trial_days_after_registration,
        "trial_extra_days_referral_registration": row.trial_extra_days_referral_registration,
        "trial_traffic_limit_gib": row.trial_traffic_limit_gib,
        "trial_traffic_limit_enabled": row.trial_traffic_limit_enabled,
        "happ_provider_id": row.happ_provider_id,
        "subscription_sub_expire_banner": row.subscription_sub_expire_banner,
        "subscription_sub_info_banner": row.subscription_sub_info_banner,
        "brand": row.brand,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_projects(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Project).order_by(Project.id))).scalars().all()
    # В списке и в деталях отдаём полные значения — админка только для super_admin.
    return [_serialize_project(r, include_secrets=True) for r in rows]


async def get_project(session: AsyncSession, project_id: int) -> dict[str, Any]:
    row = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalars().first()
    if row is None:
        raise NotFoundError(detail="Проект не найден")
    return _serialize_project(row, include_secrets=True)


async def create_project(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    data = {k: v for k, v in payload.items() if k in _PROJECT_MUTABLE_FIELDS}
    if not data.get("slug") or not data.get("name") or not data.get("primary_domain"):
        raise ConflictError(detail="Обязательны slug, name, primary_domain")
    project = Project(**data)
    session.add(project)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise ConflictError(detail=f"Не удалось создать проект: {e}") from e
    await invalidate_project_cache()
    await session.refresh(project)
    return _serialize_project(project, include_secrets=True)


async def update_project(
    session: AsyncSession, project_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    data = {k: v for k, v in payload.items() if k in _PROJECT_MUTABLE_FIELDS}
    if not data:
        return await get_project(session, project_id)
    res = await session.execute(update(Project).where(Project.id == project_id).values(**data))
    if res.rowcount == 0:
        raise NotFoundError(detail="Проект не найден")
    await session.commit()
    await invalidate_project_cache()
    return await get_project(session, project_id)


async def delete_project(session: AsyncSession, project_id: int) -> None:
    # ON DELETE RESTRICT — если есть users/payments, БД откажет 23503.
    res = await session.execute(delete(Project).where(Project.id == project_id))
    if res.rowcount == 0:
        raise NotFoundError(detail="Проект не найден")
    await session.commit()
    await invalidate_project_cache()


# =============================================
# Staff users CRUD (super_admin only).
# =============================================


def _normalize_project_ids(raw: object) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[int] = []
    for item in raw:
        try:
            pid = int(item)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in out:
            out.append(pid)
    return out


def _serialize_staff(
    row: StaffUser,
    projects: list[int] | None = None,
    project_role: str | None = None,
) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "email": row.email,
        "full_name": row.full_name,
        "role": row.role,
        "is_active": bool(row.is_active),
        "projects": projects if projects is not None else [],
        "project_role": project_role,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
    }


async def list_staff_users(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(StaffUser).order_by(StaffUser.id))).scalars().all()
    if not rows:
        return []
    ids = [int(r.id) for r in rows]
    access_rows = (
        await session.execute(
            select(
                StaffUserProjectAccess.staff_user_id,
                StaffUserProjectAccess.project_id,
                StaffUserProjectAccess.role,
            ).where(StaffUserProjectAccess.staff_user_id.in_(ids))
        )
    ).all()
    projects_by_uid: dict[int, list[int]] = {}
    project_role_by_uid: dict[int, str] = {}
    for uid, pid, access_role in access_rows:
        uid_int = int(uid)
        projects_by_uid.setdefault(uid_int, []).append(int(pid))
        project_role_by_uid.setdefault(uid_int, str(access_role))
    return [
        _serialize_staff(
            r,
            projects_by_uid.get(int(r.id), []),
            project_role_by_uid.get(int(r.id)),
        )
        for r in rows
    ]


async def create_staff_user(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = payload.get("role") or "manager"
    if role not in ("super_admin", "admin", "manager"):
        raise ConflictError(detail="Некорректная роль")
    if not email or not password:
        raise ConflictError(detail="Обязательны email и password")

    staff = StaffUser(
        email=email,
        password_hash=hash_password(password),
        full_name=payload.get("full_name"),
        role=role,
        is_active=bool(payload.get("is_active", True)),
    )
    session.add(staff)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise ConflictError(detail=f"Не удалось создать staff: {e}") from e
    await session.refresh(staff)

    project_ids = _normalize_project_ids(payload.get("projects"))
    if role != "super_admin" and not project_ids:
        raise ConflictError(detail="Укажите хотя бы один проект")
    if role != "super_admin":
        access_role = payload.get("project_role") or ("admin" if role == "admin" else "manager")
        for pid in project_ids:
            session.add(
                StaffUserProjectAccess(
                    staff_user_id=int(staff.id),
                    project_id=pid,
                    role=access_role,
                )
            )
        await session.commit()

    return _serialize_staff(
        staff,
        project_ids if role != "super_admin" else None,
        (payload.get("project_role") or ("admin" if role == "admin" else "manager"))
        if role != "super_admin"
        else None,
    )


async def update_staff_user(
    session: AsyncSession, staff_user_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field in ("full_name", "role", "is_active"):
        if field in payload:
            updates[field] = payload[field]
    if "password" in payload and payload["password"]:
        updates["password_hash"] = hash_password(payload["password"])
    if updates:
        res = await session.execute(
            update(StaffUser).where(StaffUser.id == staff_user_id).values(**updates)
        )
        if res.rowcount == 0:
            raise NotFoundError(detail="Staff не найден")

    if "role" in payload and payload["role"] == "super_admin":
        await session.execute(
            delete(StaffUserProjectAccess).where(
                StaffUserProjectAccess.staff_user_id == staff_user_id
            )
        )
    elif "projects" in payload:
        new_role = payload.get("role")
        effective_role = new_role if new_role in ("super_admin", "admin", "manager") else None
        if effective_role is None:
            row = (
                await session.execute(select(StaffUser).where(StaffUser.id == staff_user_id))
            ).scalars().first()
            effective_role = row.role if row is not None else "manager"
        project_ids = _normalize_project_ids(payload.get("projects"))
        if effective_role != "super_admin" and not project_ids:
            raise ConflictError(detail="Укажите хотя бы один проект")
        await session.execute(
            delete(StaffUserProjectAccess).where(
                StaffUserProjectAccess.staff_user_id == staff_user_id
            )
        )
        access_role = payload.get("project_role") or "manager"
        for pid in project_ids:
            session.add(
                StaffUserProjectAccess(
                    staff_user_id=int(staff_user_id),
                    project_id=pid,
                    role=access_role,
                )
            )

    await session.commit()

    row = (
        await session.execute(select(StaffUser).where(StaffUser.id == staff_user_id))
    ).scalars().first()
    if row is None:
        raise NotFoundError(detail="Staff не найден")
    access = (
        await session.execute(
            select(
                StaffUserProjectAccess.project_id,
                StaffUserProjectAccess.role,
            ).where(StaffUserProjectAccess.staff_user_id == staff_user_id)
        )
    ).all()
    project_ids = [int(r[0]) for r in access]
    project_role = str(access[0][1]) if access else None
    return _serialize_staff(row, project_ids, project_role)


async def delete_staff_user(session: AsyncSession, staff_user_id: int) -> None:
    res = await session.execute(delete(StaffUser).where(StaffUser.id == staff_user_id))
    if res.rowcount == 0:
        raise NotFoundError(detail="Staff не найден")
    await session.commit()


# =============================================
# Project tariffs CRUD.
# =============================================


def _serialize_tariff(row: ProjectTariff) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "project_id": int(row.project_id),
        "provider": row.provider,
        "months": int(row.months),
        "amount": float(row.amount),
        "name": row.name,
        "external_link": row.external_link,
        "external_tg_link": row.external_tg_link,
        "external_product_id": row.external_product_id,
        "kind": row.kind,
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order),
    }


async def list_project_tariffs(session: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ProjectTariff)
            .where(ProjectTariff.project_id == project_id)
            .order_by(ProjectTariff.provider, ProjectTariff.sort_order, ProjectTariff.months)
        )
    ).scalars().all()
    return [_serialize_tariff(r) for r in rows]


async def create_project_tariff(
    session: AsyncSession, project_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    tariff = ProjectTariff(
        project_id=project_id,
        provider=payload["provider"],
        months=int(payload.get("months") or 0),
        amount=payload.get("amount") or 0,
        name=payload.get("name"),
        external_link=payload.get("external_link"),
        external_tg_link=payload.get("external_tg_link"),
        external_product_id=payload.get("external_product_id"),
        kind=payload.get("kind"),
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order") or 0),
    )
    session.add(tariff)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise ConflictError(detail=f"Не удалось создать тариф: {e}") from e
    await session.refresh(tariff)
    return _serialize_tariff(tariff)


async def update_project_tariff(
    session: AsyncSession, tariff_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    allowed = {"months", "amount", "name", "external_link", "external_tg_link", "external_product_id",
               "kind", "is_active", "sort_order"}
    data = {k: v for k, v in payload.items() if k in allowed}
    if data:
        res = await session.execute(
            update(ProjectTariff).where(ProjectTariff.id == tariff_id).values(**data)
        )
        if res.rowcount == 0:
            raise NotFoundError(detail="Тариф не найден")
        await session.commit()
    row = (
        await session.execute(select(ProjectTariff).where(ProjectTariff.id == tariff_id))
    ).scalars().first()
    if row is None:
        raise NotFoundError(detail="Тариф не найден")
    return _serialize_tariff(row)


async def delete_project_tariff(session: AsyncSession, tariff_id: int) -> None:
    res = await session.execute(delete(ProjectTariff).where(ProjectTariff.id == tariff_id))
    if res.rowcount == 0:
        raise NotFoundError(detail="Тариф не найден")
    await session.commit()
