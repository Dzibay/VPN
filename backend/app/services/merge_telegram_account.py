"""Слияние дублирующего пользователя (Telegram-only) в целевой аккаунт веб-пользователя."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.referral_link import ReferralLink
from app.models.user import User
from app.models.user_server_traffic import UserServerTraffic
from app.services.referral_link_service import get_user_owned_referral_link


def _later_subscription(a: date | None, b: date | None) -> date | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def merge_user_server_traffic(session: Session, keep_user_id: int, drop_user_id: int) -> None:
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
    """Переносит трафик и личную реферальную ссылку с drop на keep, затем удаляет drop."""
    if keep.id == drop.id:
        return
    merge_user_server_traffic(session, keep.id, drop.id)
    merge_owned_referral_links(session, keep.id, drop.id)
    keep.subscription_until = _later_subscription(keep.subscription_until, drop.subscription_until)
    session.delete(drop)
    session.flush()
