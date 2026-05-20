"""Задачи (таблица ``tasks``) и бонусы рефереру при оплате реферируемым."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.referrals.repository import increment_referral_counter
from app.domain.tasks.notification_task_types import NOTIFY_REF_PAY
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
    """После оплаты реферируемым: ``payments_count += 1`` и задача ``notify_ref_pay``.

    Логика:

    1. Если у покупателя нет ``users.referral_link_id`` — ничего не делаем.
    2. Иначе всегда инкрементируем ``referral_links.payments_count`` (учёт воронки).
    3. Для ссылок с ``owner_kind='user'`` и владельцем ≠ покупатель:
       вычисляется ``bonus_days = paid_months × REFERRAL_BONUS_DAYS_PER_PAID_MONTH``;
       если ``bonus_days > 0`` — ставится задача ``notify_ref_pay`` с этим ``bonus_days``;
       при ``bonus_days == 0`` — задача не создаётся.

    ВАЖНО: ``users.subscription_until`` владельца здесь НЕ продлевается. Накопленные
    бонусные дни применяются к подписке владельца только при его собственной оплате
    (см. ``_handle_subscription_paid`` в ``tribute_service``): та же граница и сумма, что в
    :func:`app.domain.referrals.task_bonus_days.sum_referral_bonus_days_pending_activation`,
    прибавляются к оплаченным дням при продлении ``subscription_until``.

    Возвращает фактически зафиксированные бонусные дни (или ``None``, если задача не создана).
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

    session.add(
        Task(
            task_type=NOTIFY_REF_PAY,
            user_id=owner_id,
            referee_id=int(referee_user_id),
            bonus_days=bonus_days,
        ),
    )
    return bonus_days
