"""Журнал операций баланса пользователя и зачисление реферальных бонусов."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import USER_BALANCE_LEDGER_KIND_REFERRAL_FIRST_PAYMENT
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_balance_ledger import UserBalanceLedger


async def credit_user_balance(
    session: AsyncSession,
    *,
    user: User,
    amount_kopecks: int,
    kind: str,
    referee_id: int | None = None,
    referee_payment_id: int | None = None,
    task_id: int | None = None,
    note: str | None = None,
) -> UserBalanceLedger:
    """Зачислить сумму на ``users.balance_kopecks`` и записать строку в ledger."""
    if amount_kopecks <= 0:
        raise ValueError("amount_kopecks must be positive")

    user.balance_kopecks = int(user.balance_kopecks or 0) + int(amount_kopecks)
    entry = UserBalanceLedger(
        user_id=int(user.id),
        amount_kopecks=int(amount_kopecks),
        kind=kind,
        referee_id=referee_id,
        referee_payment_id=referee_payment_id,
        task_id=task_id,
        note=note,
    )
    session.add(entry)
    await session.flush()
    return entry


async def owner_already_credited_referral_balance_for_referee(
    session: AsyncSession,
    *,
    owner_user_id: int,
    referee_user_id: int,
) -> bool:
    """Было ли уже зачисление ``referral_first_payment`` для пары (реферер, реферируемый)."""
    stmt = (
        select(UserBalanceLedger.id)
        .where(
            UserBalanceLedger.user_id == int(owner_user_id),
            UserBalanceLedger.referee_id == int(referee_user_id),
            UserBalanceLedger.kind == USER_BALANCE_LEDGER_KIND_REFERRAL_FIRST_PAYMENT,
        )
        .limit(1)
    )
    return (await session.scalar(stmt)) is not None


async def list_user_balance_ledger(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[UserBalanceLedger], int]:
    uid = int(user_id)
    total = int(
        await session.scalar(
            select(func.count()).select_from(UserBalanceLedger).where(UserBalanceLedger.user_id == uid),
        )
        or 0,
    )
    stmt = (
        select(UserBalanceLedger)
        .where(UserBalanceLedger.user_id == uid)
        .order_by(UserBalanceLedger.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.scalars(stmt)).all())
    return rows, total
