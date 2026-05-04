"""Удаление записей subscription_devices текущего пользователя."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice


async def delete_subscription_device(
    session: AsyncSession, *, user_id: int, device_id: int,
) -> None:
    row = await session.get(SubscriptionDevice, device_id)
    if row is None or int(row.user_id) != int(user_id):
        raise NotFoundError("Подключение не найдено")
    await session.delete(row)
