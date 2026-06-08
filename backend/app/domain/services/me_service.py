"""Удаление записей subscription_devices и история оплат текущего пользователя."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.domain.models.payments import UserPaymentHistoryItem
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice


async def list_my_payments(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[UserPaymentHistoryItem], int]:
    count_stmt = select(func.count()).select_from(Payment).where(Payment.user_id == user_id)
    stmt = (
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = int(await session.scalar(count_stmt) or 0)
    rows = list((await session.scalars(stmt)).all())
    return [UserPaymentHistoryItem.model_validate(r) for r in rows], total


async def delete_subscription_device(
    session: AsyncSession, *, user_id: int, device_id: int,
) -> None:
    row = await session.get(SubscriptionDevice, device_id)
    if row is None or int(row.user_id) != int(user_id):
        raise NotFoundError("Подключение не найдено")
    await session.delete(row)
