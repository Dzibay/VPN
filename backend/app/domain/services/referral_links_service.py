"""Реферальные ссылки: оркестрация для админки и личного кабинета.

Низкоуровневые модули:

* токены — :mod:`app.domain.referrals.tokens`,
* CRUD/счётчики — :mod:`app.domain.referrals.repository`,
* сборка ответных URL — :mod:`app.domain.referrals.public_links`,
* воронка — :mod:`app.domain.referrals.funnel`.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import BearerPrincipal
from app.core.exceptions import (
    NotFoundError,
    UnauthorizedError,
)
from app.domain.referrals.public_links import referral_link_to_response
from app.domain.referrals.repository import (
    delete_referral_link,
    get_or_create_user_owned_referral_link,
)
from app.domain.referrals.task_bonus_days import (
    sum_referral_bonus_days_pending_activation,
    sum_referral_bonus_days_received_immediately,
    sum_referral_bonus_days_received_via_notify_payment,
)
from app.domain.models.referral_links import (
    ReferralTrafficBreakdown,
    ReferralTokensRegistrationsDailySummary,
    ReferralTrafficOverviewStats,
    ReferralTrafficRegistrationsDailySummary,
)
from app.domain.referrals.registrations_daily import (
    referral_tokens_registrations_daily,
    referral_traffic_registrations_daily,
)
from app.domain.tenant.admin_project_scope import (
    admin_project_id,
    apply_project_scope,
    project_scope_clause,
)
from app.domain.tenant.project_cache import get_project_by_id
from app.domain.tenant.project_context import ProjectContext, get_current_project
from app.domain.users.stats_qualification import user_counts_in_admin_stats
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


def _traffic_breakdown_from_row(row: object, prefix: str) -> ReferralTrafficBreakdown:
    return ReferralTrafficBreakdown(
        total=int(getattr(row, f"{prefix}_total") or 0),
        with_telegram_id=int(getattr(row, f"{prefix}_with_telegram_id") or 0),
        without_telegram_id=int(getattr(row, f"{prefix}_without_telegram_id") or 0),
    )


async def referral_traffic_overview_stats(session: AsyncSession) -> ReferralTrafficOverviewStats:
    """Сводка по источникам регистрации: прямой трафик, созданные ссылки, приглашения пользователей.

    Учитываются только учётные пользователи (Telegram или подтверждённый email) — как в
    ``GET /api/users/count``. Один проход по ``users`` с LEFT JOIN ``referral_links`` и
    условными агрегатами. Классификация реферального трафика — по ``referral_links.owner_user_id``:
    NULL — созданная ссылка, NOT NULL — персональная ссылка пользователя.
    """
    stats_user = user_counts_in_admin_stats(User)
    is_direct = User.referral_link_id.is_(None)
    is_channel = User.referral_link_id.is_not(None) & ReferralLink.owner_user_id.is_(None)
    is_user_referral = User.referral_link_id.is_not(None) & ReferralLink.owner_user_id.is_not(None)
    with_tg = User.telegram_id.is_not(None)
    without_tg = User.telegram_id.is_(None)

    def _counts(prefix: str, category_filter):
        return (
            func.count().filter(category_filter).label(f"{prefix}_total"),
            func.count().filter(category_filter, with_tg).label(f"{prefix}_with_telegram_id"),
            func.count().filter(category_filter, without_tg).label(f"{prefix}_without_telegram_id"),
        )

    direct_counts = _counts("direct", is_direct)
    channel_counts = _counts("channel", is_channel)
    user_ref_counts = _counts("user_ref", is_user_referral)

    scope = project_scope_clause(User)
    where_parts = [stats_user]
    if scope is not None:
        where_parts.append(scope)

    row = (
        await session.execute(
            select(*direct_counts, *channel_counts, *user_ref_counts)
            .select_from(User)
            .outerjoin(ReferralLink, User.referral_link_id == ReferralLink.id)
            .where(*where_parts),
        )
    ).one()
    return ReferralTrafficOverviewStats(
        direct=_traffic_breakdown_from_row(row, "direct"),
        channel_links=_traffic_breakdown_from_row(row, "channel"),
        user_referrals=_traffic_breakdown_from_row(row, "user_ref"),
    )


async def referral_tokens_registrations_daily_summary(
    session: AsyncSession,
    *,
    days: int = 30,
    min_registrations: int = 10,
) -> ReferralTokensRegistrationsDailySummary:
    """Регистрации по дням МСК для токенов с registrations_count > min_registrations."""
    return await referral_tokens_registrations_daily(
        session,
        days=days,
        min_registrations=min_registrations,
    )


async def referral_traffic_registrations_daily_summary(
    session: AsyncSession,
    *,
    days: int = 30,
) -> ReferralTrafficRegistrationsDailySummary:
    """Регистрации по дням МСК с разбивкой по источникам трафика."""
    return await referral_traffic_registrations_daily(session, days=days)


async def _referral_links_revenue_by_id(session: AsyncSession) -> dict[int, Decimal]:
    stmt = (
        select(User.referral_link_id, func.coalesce(func.sum(Payment.net_amount), 0))
        .select_from(User)
        .join(Payment, Payment.user_id == User.id)
        .where(User.referral_link_id.is_not(None))
        .group_by(User.referral_link_id)
    )
    scope = project_scope_clause(User)
    if scope is not None:
        stmt = stmt.where(scope)
    rows = (await session.execute(stmt)).all()
    return {
        int(link_id): Decimal(str(total))
        for link_id, total in rows
        if link_id is not None
    }


async def _referral_link_revenue_net(session: AsyncSession, link_id: int) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(Payment.net_amount), 0))
        .select_from(User)
        .join(Payment, Payment.user_id == User.id)
        .where(User.referral_link_id == link_id)
    )
    scope = project_scope_clause(User)
    if scope is not None:
        stmt = stmt.where(scope)
    total = await session.scalar(stmt)
    return Decimal(str(total or 0))


async def _project_context_for_link(link: ReferralLink) -> ProjectContext | None:
    """Проект ссылки из кэша; иначе контекст текущего запроса."""
    project = await get_project_by_id(int(link.project_id))
    if project is not None:
        return project
    return get_current_project()


async def list_staff_referral_links(session: AsyncSession, cfg: object) -> list:
    """Все реферальные записи в админке, новейшие первыми; URL подставляются из ``cfg``."""
    stmt = apply_project_scope(
        select(ReferralLink).order_by(ReferralLink.id.desc()),
        ReferralLink,
    )
    rows = list((await session.scalars(stmt)).all())
    revenues = await _referral_links_revenue_by_id(session)
    project_ids = {int(r.project_id) for r in rows}
    projects: dict[int, ProjectContext] = {}
    for pid in project_ids:
        p = await get_project_by_id(pid)
        if p is not None:
            projects[pid] = p
    fallback = get_current_project()
    return [
        referral_link_to_response(
            r,
            cfg,
            project=projects.get(int(r.project_id), fallback),
            revenue_net=revenues.get(int(r.id), Decimal("0")),
        )
        for r in rows
    ]


async def get_staff_referral_link_by_id(session: AsyncSession, link_id: int, cfg: object):
    """Одна запись для админки; 404 если не найдена."""
    row = await session.get(ReferralLink, link_id)
    if row is None:
        raise NotFoundError("Токен не найден")
    pid = admin_project_id()
    if pid is not None and int(row.project_id) != pid:
        raise NotFoundError("Токен не найден")
    revenue_net = await _referral_link_revenue_net(session, link_id)
    project = await _project_context_for_link(row)
    return referral_link_to_response(row, cfg, project=project, revenue_net=revenue_net)


async def delete_referral_link_row(session: AsyncSession, link_id: int) -> None:
    """Удалить запись по id; 404 если не найдена."""
    if not await delete_referral_link(session, link_id):
        raise NotFoundError("Токен не найден")


def referral_me_user_id_from_bearer(principal: BearerPrincipal) -> int:
    """Идентификатор учётной записи для персональной реферальной ссылки (роли user, manager, admin)."""
    if principal.user_id is None:
        raise UnauthorizedError("Недействительный токен")
    return int(principal.user_id)


async def referral_me_for_user(session: AsyncSession, user_id: int, cfg: object):
    """Получить (или создать) персональную ссылку пользователя и вернуть её для /me.

    Доменные ошибки (пользователь не найден, не удалось сгенерировать токен) — это
    подклассы :class:`AppError`, которые поднимаются как есть и маппятся глобальным обработчиком.
    """
    from app.domain.models.referral_links import ReferralMeResponse

    row = await get_or_create_user_owned_referral_link(session, user_id)

    project = await get_project_by_id(int(row.project_id))
    if project is None:
        user = await session.get(User, user_id)
        if user is not None:
            project = await get_project_by_id(int(user.project_id))

    pending, received_from_payments, received_immediately = await asyncio.gather(
        sum_referral_bonus_days_pending_activation(session, user_id=user_id),
        sum_referral_bonus_days_received_via_notify_payment(session, user_id=user_id),
        sum_referral_bonus_days_received_immediately(session, user_id=user_id),
    )
    return ReferralMeResponse(
        link=referral_link_to_response(row, cfg, project=project),
        bonus_days_pending_activation=pending,
        bonus_days_received=received_from_payments + received_immediately,
    )
