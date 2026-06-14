"""Staff API: журнал баланса пользователя."""

from __future__ import annotations

from app.domain.balance.ledger import list_user_balance_ledger
from app.domain.balance.money import kopecks_to_rub
from app.domain.models.user_balance import UserBalanceLedgerItem, UserBalanceLedgerListResponse
from app.domain.services.users_service import require_user_exists
from sqlalchemy.ext.asyncio import AsyncSession


async def staff_user_balance_ledger(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> UserBalanceLedgerListResponse:
    await require_user_exists(session, user_id)
    rows, total = await list_user_balance_ledger(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    items = [
        UserBalanceLedgerItem(
            id=int(row.id),
            amount_rub=kopecks_to_rub(int(row.amount_kopecks)),
            kind=row.kind,
            referee_id=row.referee_id,
            referee_payment_id=row.referee_payment_id,
            task_id=row.task_id,
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return UserBalanceLedgerListResponse(items=items, total=total)
