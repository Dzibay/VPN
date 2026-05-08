"""Задачи (таблица ``tasks``) и бонусы рефереру при оплате реферируемым."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.time import utc_today
from app.domain.referrals.repository import increment_referral_counter
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User


async def apply_referral_bonus_on_payment(
    session: AsyncSession,
    *,
    settings: Settings,
    referee_user_id: int,
    paid_months: int,
) -> int | None:
    """После оплаты реферируемым: ``payments_count += 1``, бонус и ``notify_ref_pay``.

    Логика:

    1. Если у покупателя нет ``users.referral_link_id`` — ничего не делаем.
    2. Иначе всегда инкрементируем ``referral_links.payments_count`` (учёт воронки).
    3. Для ссылок с ``owner_kind='user'`` и владельцем ≠ покупатель:
       вычисляется ``bonus_days = paid_months × REFERRAL_BONUS_DAYS_PER_PAID_MONTH``;
       если ``bonus_days > 0`` — продлеваем ``users.subscription_until`` владельца ссылки
       (от ``max(today, current)``) и ставим в ``tasks`` задачу ``notify_ref_pay`` с этим ``bonus_days``;
       при ``bonus_days == 0`` — задачу не ставим, продление не делаем.

    Возвращает фактически начисленные бонусные дни (или ``None``, если задача не создана).
    """

    user_stmt = select(User).where(User.id == int(referee_user_id)).limit(1)
    user = (await session.scalars(user_stmt)).first()
    if user is None or user.referral_link_id is None:
        return None

    link_stmt = select(ReferralLink).where(ReferralLink.id == int(user.referral_link_id)).limit(1)
    link = (await session.scalars(link_stmt)).first()
    if link is None:
        return None

    await increment_referral_counter(session, int(link.id), "payments")

    if link.owner_kind != "user" or link.owner_user_id is None:
        return None
    owner_id = int(link.owner_user_id)
    if owner_id == int(referee_user_id):
        return None

    per_month = int(settings.referral_bonus_days_per_paid_month)
    bonus_days = per_month * int(paid_months)
    if bonus_days <= 0:
        return None

    owner_stmt = select(User).where(User.id == owner_id).limit(1)
    owner = (await session.scalars(owner_stmt)).first()
    if owner is not None and owner.subscription_until is not None:
        today = utc_today()
        base = owner.subscription_until if owner.subscription_until >= today else today
        owner.subscription_until = base + timedelta(days=bonus_days)

    session.add(
        Task(
            task_type="notify_ref_pay",
            user_id=owner_id,
            referee_id=int(referee_user_id),
            bonus_days=bonus_days,
        ),
    )
    return bonus_days
