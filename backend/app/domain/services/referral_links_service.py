"""Реферальные ссылки: оркестрация для админки и личного кабинета.

Низкоуровневые модули:

* токены — :mod:`app.domain.referrals.tokens`,
* CRUD/счётчики — :mod:`app.domain.referrals.repository`,
* сборка ответных URL — :mod:`app.domain.referrals.public_links`,
* воронка — :mod:`app.domain.referrals.funnel`.
"""

from __future__ import annotations

from sqlalchemy import select
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
from app.infrastructure.persistence.models.referral_link import ReferralLink


async def list_staff_referral_links(session: AsyncSession, cfg: object) -> list:
    """Все реферальные записи в админке, новейшие первыми; URL подставляются из ``cfg``."""
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list((await session.scalars(stmt)).all())
    return [referral_link_to_response(r, cfg) for r in rows]


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

    return ReferralMeResponse(link=referral_link_to_response(row, cfg))
