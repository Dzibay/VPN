"""Задачи (таблица ``tasks``) и бонусы рефереру при оплате реферируемым."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.constants import USER_BALANCE_LEDGER_KIND_REFERRAL_FIRST_PAYMENT
from app.domain.balance.ledger import credit_user_balance, owner_already_credited_referral_balance_for_referee
from app.domain.referrals.referral_bonus_policy import (
    compute_referral_balance_bonus_kopecks_for_owner,
    compute_referral_bonus_days_for_owner,
    normalize_referral_bonus_policy,
    owner_already_rewarded_for_referee_payment,
    referral_bonus_applies_immediately,
    referral_bonus_policy_is_balance,
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
    referee_payment_id: int | None = None,
) -> int | None:
    """После оплаты реферируемым: ``payments_count += 1`` и задача ``notify_ref_pay``.

    Логика:

    1. Если у покупателя нет ``users.referral_link_id`` — ничего не делаем.
    2. Иначе всегда инкрементируем ``referral_links.payments_count`` (учёт воронки).
    3. Для ссылок с ``owner_kind='user'`` и владельцем ≠ покупатель:
       бонус зависит от ``users.referral_bonus_policy`` владельца (см.
       :func:`compute_referral_bonus_days_for_owner` и
       :func:`compute_referral_balance_bonus_kopecks_for_owner`).

    Политика ``default``: бонус = ``paid_months × REFERRAL_BONUS_DAYS_PER_PAID_MONTH``,
    ``subscription_until`` владельца здесь НЕ продлевается — дни копятся до его оплаты.

    Политика ``fixed_first_payment_instant``: фиксированные дни только при первой
    оплате каждого реферируемого; ``subscription_until`` продлевается сразу.

    Политика ``fixed_first_payment_balance``: фиксированная сумма на ``users.balance_kopecks``
    только при первой оплате каждого реферируемого; запись в ``user_balance_ledger``.

    Возвращает фактически зафиксированные бонусные дни (или ``None``, если дни не начислялись).
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

    if referral_bonus_policy_is_balance(policy):
        return await _apply_referral_balance_bonus_on_payment(
            session,
            settings=settings,
            owner=owner,
            referee_user_id=int(referee_user_id),
            referee_payment_id=referee_payment_id,
            policy=policy,
            is_first_referee_payment=is_first_referee_payment,
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


async def _apply_referral_balance_bonus_on_payment(
    session: AsyncSession,
    *,
    settings: Settings,
    owner: User,
    referee_user_id: int,
    referee_payment_id: int | None,
    policy: str,
    is_first_referee_payment: bool,
) -> None:
    if not is_first_referee_payment:
        return None
    if await owner_already_credited_referral_balance_for_referee(
        session,
        owner_user_id=int(owner.id),
        referee_user_id=referee_user_id,
    ):
        return None

    amount_kopecks = compute_referral_balance_bonus_kopecks_for_owner(
        policy=policy,
        owner=owner,
        settings=settings,
        is_first_referee_payment=True,
    )
    if amount_kopecks <= 0:
        return None

    task = Task(
        task_type=NOTIFY_REF_PAY,
        user_id=int(owner.id),
        referee_id=referee_user_id,
        bonus_amount_kopecks=amount_kopecks,
        referral_bonus_applied=True,
    )
    session.add(task)
    await session.flush()

    await credit_user_balance(
        session,
        user=owner,
        amount_kopecks=amount_kopecks,
        kind=USER_BALANCE_LEDGER_KIND_REFERRAL_FIRST_PAYMENT,
        referee_id=referee_user_id,
        referee_payment_id=referee_payment_id,
        task_id=int(task.id),
    )
    return None
