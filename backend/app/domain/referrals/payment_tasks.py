"""Задачи (таблица ``tasks``) и бонусы рефереру при оплате реферируемым."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.referrals.referral_bonus_policy import (
    compute_referral_bonus_days_for_owner,
    normalize_referral_bonus_policy,
    owner_already_rewarded_for_referee_payment,
    referral_bonus_applies_immediately,
)
from app.domain.referrals.repository import increment_referral_counter
from app.domain.tasks.eligibility import async_user_has_telegram_id
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
       бонусные дни зависят от ``users.referral_bonus_policy`` владельца (см.
       :func:`compute_referral_bonus_days_for_owner`); при ``bonus_days > 0`` —
       задача ``notify_ref_pay``; при ``bonus_days == 0`` — задача не создаётся.

    Политика ``default``: бонус = ``paid_months × REFERRAL_BONUS_DAYS_PER_PAID_MONTH``,
    ``subscription_until`` владельца здесь НЕ продлевается — дни копятся до его оплаты.

    Политика ``fixed_first_payment_instant``: фиксированные дни только при первой
    оплате каждого реферируемого; ``subscription_until`` продлевается сразу.

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

    owner_stmt = select(User).where(User.id == owner_id).limit(1)
    owner = (await session.scalars(owner_stmt)).first()
    if owner is None:
        return None

    policy = normalize_referral_bonus_policy(owner.referral_bonus_policy)
    is_first_referee_payment = not await owner_already_rewarded_for_referee_payment(
        session,
        owner_user_id=owner_id,
        referee_user_id=int(referee_user_id),
    )
    bonus_days = compute_referral_bonus_days_for_owner(
        policy=policy,
        paid_months=int(paid_months),
        settings=settings,
        is_first_referee_payment=is_first_referee_payment,
    )
    if bonus_days <= 0:
        return None
    if not await async_user_has_telegram_id(session, owner_id):
        return None

    apply_immediately = referral_bonus_applies_immediately(policy)
    if apply_immediately:
        from app.domain.services.payment_service import extend_subscription_until
        from app.domain.subscription.traffic_limit import (
            enqueue_xray_clients_sync_for_access_change,
        )

        owner.subscription_until = extend_subscription_until(
            owner.subscription_until,
            days=bonus_days,
        )
        enqueue_xray_clients_sync_for_access_change()

    session.add(
        Task(
            task_type=NOTIFY_REF_PAY,
            user_id=owner_id,
            referee_id=int(referee_user_id),
            bonus_days=bonus_days,
            referral_bonus_applied=apply_immediately,
        ),
    )
    return bonus_days
