"""Реферальные ссылки: оркестрация для админки и личного кабинета.

Низкоуровневые модули:

* токены — :mod:`app.domain.referrals.tokens`,
* CRUD/счётчики — :mod:`app.domain.referrals.repository`,
* сборка ответных URL — :mod:`app.domain.referrals.public_links`,
* воронка — :mod:`app.domain.referrals.funnel`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ForbiddenError,
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


def list_staff_referral_links(session: Session, cfg: object) -> list:
    """Все реферальные записи в админке, новейшие первыми; URL подставляются из ``cfg``."""
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list(session.scalars(stmt).all())
    return [referral_link_to_response(r, cfg) for r in rows]


def delete_referral_link_row(session: Session, link_id: int) -> None:
    """Удалить запись по id; 404 если не найдена."""
    if not delete_referral_link(session, link_id):
        raise NotFoundError("Токен не найден")


def client_site_user_id(principal: object) -> int:
    """Извлечь ``user_id`` из принципала только если роль = ``user`` (для /me-эндпоинтов).

    Сотрудникам (``manager``/``admin``) персональная ссылка недоступна — они работают со всеми
    ссылками через админ-панель и не должны вешать клики на свои аккаунты.
    """
    role = getattr(principal, "role", None)
    uid = getattr(principal, "user_id", None)
    if role != "user":
        raise ForbiddenError(
            "Персональная реферальная ссылка доступна только для учётной записи "
            "клиента (токены для сотрудников — через админ-панель).",
        )
    if uid is None:
        raise UnauthorizedError("Недействительный токен")
    return int(uid)


def referral_me_for_user(session: Session, user_id: int, cfg: object):
    """Получить (или создать) персональную ссылку пользователя и вернуть её для /me."""
    from app.domain.models.referral_links import ReferralMeResponse

    try:
        row = get_or_create_user_owned_referral_link(session, user_id)
    except ValueError as e:
        msg = str(e)
        if msg == "Пользователь не найден":
            raise NotFoundError(msg) from e
        raise UnprocessableEntityError(msg) from e
    except RuntimeError as e:
        raise InternalServerError(str(e)) from e

    return ReferralMeResponse(link=referral_link_to_response(row, cfg))
