"""Bootstrap staff_users и projects из env-переменных.

Идея: администратор задаёт список аккаунтов (super_admin + admin/manager с проектами)
и список проектов в ``.env`` — при каждом старте API система приводит БД к этому состоянию.

Что делается:

- **projects (BOOTSTRAP_PROJECTS)**: создаются/обновляются проекты по slug. Обновляются
  только name/primary_domain/extra_domains — остальные поля (ключи, брендинг) не трогаем,
  чтобы не затирать значения, введённые через админку.

- **super_admins (STAFF_SUPER_ADMINS)**: создаются/обновляются super_admin аккаунты.
  Пароль в env — источник истины (при каждом старте перезаписывается). Роль обновляется
  до super_admin. Проекты для super_admin не важны (роль даёт доступ ко всем).

- **managers (STAFF_MANAGERS)**: создаются/обновляются admin/manager аккаунты.
  Пароль, роль и доступ к проектам синхронизируются: удаляются лишние записи из
  ``staff_user_project_access``, добавляются новые.

Legacy (STAFF_ADMIN_EMAIL/PASSWORD) — если STAFF_SUPER_ADMINS пустой, но заданы
legacy-поля — они трактуются как одна запись super_admin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.passwords import hash_password
from app.core.time import utc_now
from app.infrastructure.persistence.models.project import Project
from app.infrastructure.persistence.models.staff_user import StaffUser
from app.infrastructure.persistence.models.staff_user_project_access import (
    StaffUserProjectAccess,
)

log = logging.getLogger("app.tenant.staff_bootstrap")


# =====================================================================
# Парсеры env-строк.
# =====================================================================

@dataclass(frozen=True)
class _StaffSpec:
    email: str
    password: str
    role: str  # super_admin | admin | manager
    projects: list[str]  # slugs; для super_admin игнорируется


@dataclass(frozen=True)
class _ProjectSpec:
    slug: str
    name: str
    primary_domain: str
    extra_domains: list[str]


def _parse_super_admins(raw: str) -> list[_StaffSpec]:
    out: list[_StaffSpec] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 2:
            log.warning("STAFF_SUPER_ADMINS: пропущена запись без пароля: %r", chunk)
            continue
        email = parts[0].strip().lower()
        password = parts[1].strip()
        if not email or not password:
            log.warning("STAFF_SUPER_ADMINS: пустой email/password в %r", chunk)
            continue
        if len(password) < 8:
            log.error("STAFF_SUPER_ADMINS %s: пароль короче 8 символов, пропуск", email)
            continue
        out.append(_StaffSpec(email=email, password=password, role="super_admin", projects=[]))
    return out


def _parse_managers(raw: str) -> list[_StaffSpec]:
    out: list[_StaffSpec] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 4:
            log.warning(
                "STAFF_MANAGERS: запись должна иметь 4 части (email|password|role|slugs), got %r", chunk
            )
            continue
        email = parts[0].strip().lower()
        password = parts[1].strip()
        role = parts[2].strip().lower()
        slugs_raw = parts[3].strip()
        if role not in ("admin", "manager"):
            log.error("STAFF_MANAGERS %s: неизвестная роль %r (ожидалось admin|manager)", email, role)
            continue
        if not email or not password:
            log.warning("STAFF_MANAGERS: пустой email/password в %r", chunk)
            continue
        if len(password) < 8:
            log.error("STAFF_MANAGERS %s: пароль короче 8 символов, пропуск", email)
            continue
        slugs = [s.strip().lower() for s in slugs_raw.split(";") if s.strip()]
        out.append(_StaffSpec(email=email, password=password, role=role, projects=slugs))
    return out


def _parse_projects(raw: str) -> list[_ProjectSpec]:
    out: list[_ProjectSpec] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 3:
            log.warning(
                "BOOTSTRAP_PROJECTS: запись должна иметь 3-4 части "
                "(slug|name|primary_domain|extras), got %r", chunk,
            )
            continue
        slug = parts[0].strip().lower()
        name = parts[1].strip()
        primary_domain = parts[2].strip().lower()
        extras_raw = parts[3].strip() if len(parts) >= 4 else ""
        if not slug or not name or not primary_domain:
            log.warning("BOOTSTRAP_PROJECTS: пустые обязательные поля в %r", chunk)
            continue
        extras = [d.strip().lower() for d in extras_raw.split(";") if d.strip()]
        out.append(_ProjectSpec(slug=slug, name=name, primary_domain=primary_domain, extra_domains=extras))
    return out


# =====================================================================
# Bootstrap логика.
# =====================================================================

async def _bootstrap_projects(session: AsyncSession, specs: list[_ProjectSpec]) -> bool:
    """Создаёт/обновляет проекты. Возвращает True, если было изменение (для инвалидации кэша)."""
    if not specs:
        return False
    changed = False
    for spec in specs:
        row = (
            await session.execute(select(Project).where(Project.slug == spec.slug))
        ).scalars().first()
        if row is None:
            brand = None
            if spec.slug == "halyal":
                brand = {"frontend_mode": "placeholder", "brand_name": "Halyal VPN"}
            row = Project(
                slug=spec.slug,
                name=spec.name,
                primary_domain=spec.primary_domain,
                extra_domains=spec.extra_domains,
                is_active=True,
                brand=brand,
            )
            session.add(row)
            log.info("BOOTSTRAP_PROJECTS: создан проект %s (%s)", spec.slug, spec.primary_domain)
            changed = True
        else:
            local_changed = False
            if row.name != spec.name:
                row.name = spec.name
                local_changed = True
            if (row.primary_domain or "").lower() != spec.primary_domain:
                row.primary_domain = spec.primary_domain
                local_changed = True
            current_extras = sorted(list(row.extra_domains or []))
            if current_extras != sorted(spec.extra_domains):
                row.extra_domains = spec.extra_domains
                local_changed = True
            if local_changed:
                log.info("BOOTSTRAP_PROJECTS: обновлён проект %s", spec.slug)
                changed = True
    if changed:
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("BOOTSTRAP_PROJECTS: ошибка коммита")
            return False
    return changed


async def _upsert_staff(session: AsyncSession, spec: _StaffSpec) -> StaffUser | None:
    """Создаёт или обновляет staff. Возвращает None при ошибке."""
    row = (
        await session.execute(select(StaffUser).where(StaffUser.email == spec.email))
    ).scalars().first()
    if row is None:
        row = StaffUser(
            email=spec.email,
            password_hash=hash_password(spec.password),
            full_name=f"Bootstrap {spec.role}",
            role=spec.role,
            is_active=True,
        )
        session.add(row)
        log.info("STAFF bootstrap: создан %s (%s)", spec.email, spec.role)
    else:
        row.password_hash = hash_password(spec.password)
        row.role = spec.role
        row.is_active = True
        log.info("STAFF bootstrap: обновлён %s (%s)", spec.email, spec.role)
    try:
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()
        log.exception("STAFF bootstrap: не удалось сохранить %s", spec.email)
        return None
    await session.refresh(row)
    return row


async def _sync_staff_project_access(
    session: AsyncSession, staff: StaffUser, slugs: list[str]
) -> None:
    """Синхронизирует staff_user_project_access под указанный список slug'ов."""
    if staff.role == "super_admin":
        # У super_admin доступ ко всем — таблицу связей чистим (она не нужна).
        await session.execute(
            delete(StaffUserProjectAccess).where(
                StaffUserProjectAccess.staff_user_id == staff.id
            )
        )
        await session.commit()
        return

    # Резолвим slug'и → project_id (только *, либо список).
    expand_all = "*" in slugs
    if expand_all:
        rows = (await session.execute(select(Project))).scalars().all()
        target_ids = {int(r.id) for r in rows}
    else:
        rows = (
            await session.execute(select(Project).where(Project.slug.in_(slugs)))
        ).scalars().all()
        target_ids = {int(r.id) for r in rows}
        missing = set(slugs) - {r.slug for r in rows}
        if missing:
            log.warning(
                "STAFF bootstrap %s: неизвестные slug проектов, пропущены: %s",
                staff.email, sorted(missing),
            )

    current = (
        await session.execute(
            select(StaffUserProjectAccess.project_id).where(
                StaffUserProjectAccess.staff_user_id == staff.id
            )
        )
    ).all()
    current_ids = {int(r[0]) for r in current}

    to_add = target_ids - current_ids
    to_remove = current_ids - target_ids

    for pid in to_add:
        session.add(
            StaffUserProjectAccess(
                staff_user_id=int(staff.id), project_id=int(pid), role=staff.role
            )
        )
    if to_remove:
        await session.execute(
            delete(StaffUserProjectAccess).where(
                StaffUserProjectAccess.staff_user_id == staff.id,
                StaffUserProjectAccess.project_id.in_(to_remove),
            )
        )
    if to_add or to_remove:
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("STAFF bootstrap %s: ошибка синхронизации project_access", staff.email)


async def bootstrap_from_env(session: AsyncSession, settings: Settings) -> None:
    """Главная точка входа: idempotent-приведение projects и staff_users к env."""
    # 0. Клиентская таблица users — только role=client; admin/manager → staff_users.
    from sqlalchemy import update as sa_update
    from app.infrastructure.persistence.models.user import User

    demoted = await session.execute(
        sa_update(User)
        .where(User.account_role.in_(("admin", "manager")))
        .values(account_role="client")
    )
    if demoted.rowcount:
        log.info(
            "users: сброшено %d записей admin/manager → client (staff только в staff_users)",
            demoted.rowcount,
        )
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("users demote: ошибка коммита")

    # 1. Проекты сначала — чтобы staff-managers могли на них ссылаться.
    project_specs = _parse_projects(settings.bootstrap_projects)
    projects_changed = await _bootstrap_projects(session, project_specs)

    if projects_changed:
        # Кэш проектов должен подхватить новые домены.
        try:
            from app.domain.tenant.project_cache import invalidate as _invalidate_projects
            await _invalidate_projects()
        except Exception:  # noqa: BLE001
            log.exception("Не удалось инвалидировать project cache после bootstrap")

    # 2. Super admins: сначала новое поле, потом legacy fallback.
    supers = _parse_super_admins(settings.staff_super_admins)
    if not supers:
        legacy_email = (settings.staff_admin_email or "").strip().lower()
        legacy_pw = settings.staff_admin_password or ""
        if legacy_email and legacy_pw and len(legacy_pw) >= 8:
            supers = [_StaffSpec(email=legacy_email, password=legacy_pw, role="super_admin", projects=[])]

    managers = _parse_managers(settings.staff_managers)

    if not supers and not managers:
        # Ничего не делаем; но если БД пуста — предупреждаем.
        count = (await session.execute(select(StaffUser))).first()
        if count is None:
            log.warning(
                "staff_users пуст и STAFF_SUPER_ADMINS/STAFF_MANAGERS не заданы: "
                "залогиниться в админку невозможно. Заведите super_admin в .env или SQL-ом."
            )
        return

    for spec in supers:
        staff = await _upsert_staff(session, spec)
        if staff is not None:
            await _sync_staff_project_access(session, staff, spec.projects)

    for spec in managers:
        staff = await _upsert_staff(session, spec)
        if staff is not None:
            await _sync_staff_project_access(session, staff, spec.projects)


# =====================================================================
# Обратно-совместимый alias для legacy-вызова из main.py.
# =====================================================================

async def bootstrap_first_super_admin(session: AsyncSession, settings: Settings) -> None:
    """Совместимость с прежней сигнатурой: делегирует в bootstrap_from_env."""
    await bootstrap_from_env(session, settings)
