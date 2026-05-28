"""Реферальные ссылки: оркестрация для админки и личного кабинета.

Низкоуровневые модули:

* токены — :mod:`app.domain.referrals.tokens`,
* CRUD/счётчики — :mod:`app.domain.referrals.repository`,
* сборка ответных URL — :mod:`app.domain.referrals.public_links`,
* воронка — :mod:`app.domain.referrals.funnel`.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import BearerPrincipal
from app.core.exceptions import (
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
    UnprocessableEntityError,
)
from app.domain.referrals.public_links import referral_link_to_response
from app.domain.referrals.repository import (
    delete_referral_link,
    get_or_create_user_owned_referral_link,
)
from app.domain.referrals.task_bonus_days import (
    sum_referral_bonus_days_pending_activation,
    sum_referral_bonus_days_received_via_notify_payment,
)
from app.domain.models.referral_links import ReferralDirectTrafficStats
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


async def direct_traffic_users_stats(session: AsyncSession) -> ReferralDirectTrafficStats:
    """Число пользователей без referral_link_id, с разбивкой по наличию telegram_id."""
    row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(User.telegram_id.is_not(None)).label("with_telegram_id"),
                func.count().filter(User.telegram_id.is_(None)).label("without_telegram_id"),
            )
            .select_from(User)
            .where(User.referral_link_id.is_(None)),
        )
    ).one()
    return ReferralDirectTrafficStats(
        total=int(row.total or 0),
        with_telegram_id=int(row.with_telegram_id or 0),
        without_telegram_id=int(row.without_telegram_id or 0),
    )


async def list_staff_referral_links(session: AsyncSession, cfg: object) -> list:
    """Все реферальные записи в админке, новейшие первыми; URL подставляются из ``cfg``."""
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list((await session.scalars(stmt)).all())
    return [referral_link_to_response(r, cfg) for r in rows]


async def get_staff_referral_link_by_id(session: AsyncSession, link_id: int, cfg: object):
    """Одна запись для админки; 404 если не найдена."""
    row = await session.get(ReferralLink, link_id)
    if row is None:
        raise NotFoundError("Токен не найден")
    return referral_link_to_response(row, cfg)


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
    """Получить (или создать) персональную ссылку пользователя и вернуть её для /me."""
    from app.domain.models.referral_links import ReferralMeResponse

    try:
        row = await get_or_create_user_owned_referral_link(session, user_id)
    except ValueError as e:
        msg = str(e)
        if msg == "Пользователь не найден":
            raise NotFoundError(msg) from e
        raise UnprocessableEntityError(msg) from e
    except RuntimeError as e:
        raise InternalServerError(str(e)) from e

    pending, received = await asyncio.gather(
        sum_referral_bonus_days_pending_activation(session, user_id=user_id),
        sum_referral_bonus_days_received_via_notify_payment(session, user_id=user_id),
    )
    return ReferralMeResponse(
        link=referral_link_to_response(row, cfg),
        bonus_days_pending_activation=pending,
        bonus_days_received=received,
    )
