"""Удаление записей subscription_devices текущего пользователя."""

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice


def delete_subscription_device(session: Session, *, user_id: int, device_id: int) -> None:
    row = session.get(SubscriptionDevice, device_id)
    if row is None or int(row.user_id) != int(user_id):
        raise NotFoundError("Подключение не найдено")
    session.delete(row)
