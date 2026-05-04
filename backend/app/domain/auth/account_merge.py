"""Объединение двух учётных записей пользователя в одну.

Используется при привязке Telegram к существующему сайтовому аккаунту: если в БД уже есть
запись с тем же ``telegram_id``, нужно перенести трафик и реферальную ссылку на основной
аккаунт и удалить дубликат, не теряя пользовательских данных.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.referrals.repository import get_user_owned_referral_link
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


def _later_subscription_date(a: date | None, b: date | None) -> date | None:
    """Самая поздняя из двух дат окончания подписки.

    После слияния учёток у итогового пользователя должно остаться больше календарных дней
    доступа из двух (пример: +10 дней vs +14 дней → остаётся +14).
    """
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def merge_user_server_traffic(session: Session, keep_user_id: int, drop_user_id: int) -> None:
    """Перенести строки ``user_server_traffic`` с ``drop_user_id`` на ``keep_user_id``.

    При коллизии (тот же сервер и день) суммирует счётчики, иначе — переподвешивает строку.
    """
    rows = session.scalars(
        select(UserServerTraffic).where(UserServerTraffic.user_id == drop_user_id),
    ).all()
    for row in rows:
        exist = session.get(
            UserServerTraffic,
            {
                "user_id": keep_user_id,
                "server_id": row.server_id,
                "traffic_date": row.traffic_date,
            },
        )
        if exist is None:
            session.add(
                UserServerTraffic(
                    user_id=keep_user_id,
                    server_id=row.server_id,
                    traffic_date=row.traffic_date,
                    up_bytes=row.up_bytes,
                    down_bytes=row.down_bytes,
                    raw_up=row.raw_up,
                    raw_down=row.raw_down,
                ),
            )
        else:
            exist.up_bytes += row.up_bytes
            exist.down_bytes += row.down_bytes
            exist.raw_up += row.raw_up
            exist.raw_down += row.raw_down
        session.delete(row)


def merge_owned_referral_links(session: Session, keep_user_id: int, drop_user_id: int) -> None:
    """Перенести личную реферальную ссылку с ``drop`` на ``keep``.

    Если у обоих были собственные ссылки — складывает счётчики на ссылку ``keep``
    и удаляет ссылку ``drop``; если ссылка только у ``drop`` — переподвешивает её.
    """
    la = get_user_owned_referral_link(session, keep_user_id)
    lb = get_user_owned_referral_link(session, drop_user_id)
    if lb is None:
        return
    if la is None:
        lb.owner_user_id = keep_user_id
        session.flush()
        return
    la.clicks_count += lb.clicks_count
    la.registrations_count += lb.registrations_count
    la.payments_count += lb.payments_count
    session.delete(lb)
    session.flush()


def merge_drop_user_into_keep(session: Session, keep: User, drop: User) -> None:
    """Перенести трафик и личную реферальную ссылку с ``drop`` на ``keep``, затем удалить ``drop``.

    ``subscription_until`` у ``keep`` становится более поздней из двух дат (максимум остатка
    подписки).
    """
    if keep.id == drop.id:
        return
    merge_user_server_traffic(session, keep.id, drop.id)
    merge_owned_referral_links(session, keep.id, drop.id)
    keep.subscription_until = _later_subscription_date(keep.subscription_until, drop.subscription_until)
    session.delete(drop)
    session.flush()
