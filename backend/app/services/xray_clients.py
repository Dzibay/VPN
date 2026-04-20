"""
Список UUID клиентов VLESS для записи в inbound Xray: активные подписки + fallback на UUID узла.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.server import Server
from app.models.user import User


def active_subscription_user_uuids(session: Session) -> list[str]:
    """UUID пользователей с действующей подпиской (без срока или дата ≥ сегодня)."""
    stmt: Select[tuple[str]] = select(User.vless_uuid).where(
        or_(
            User.subscription_until.is_(None),
            User.subscription_until >= date.today(),
        )
    )
    rows = session.scalars(stmt).all()
    out: list[str] = []
    seen: set[str] = set()
    for u in rows:
        s = (u or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def vless_client_uuids_csv_for_server(session: Session, server: Server) -> str:
    """
    Строка UUID через запятую для VPN_VLESS_CLIENT_UUIDS.
    Если нет ни одного активного пользователя — в конфиг попадает только UUID узла (fallback).
    """
    uuids = active_subscription_user_uuids(session)
    fallback = (server.vless_uuid or "").strip()
    if not uuids:
        if fallback:
            return fallback
        return ""
    return ",".join(uuids)
