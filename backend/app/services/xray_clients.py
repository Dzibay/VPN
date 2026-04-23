"""
Список клиентов VLESS для Xray: активные подписки + fallback на UUID узла.
"""

from __future__ import annotations

import base64
import json
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.domain.subscription import subscription_active_sql
from app.models.server import Server
from app.models.user import User


def active_subscription_users(session: Session) -> list[User]:
    stmt: Select[User] = (
        select(User)
        .where(subscription_active_sql())
        .order_by(User.id.asc())
    )
    return list(session.scalars(stmt).all())


def active_subscription_user_uuids(session: Session) -> list[str]:
    """UUID пользователей с действующей подпиской (без срока или дата ≥ сегодня)."""
    out: list[str] = []
    seen: set[str] = set()
    for u in active_subscription_users(session):
        s = (u.vless_uuid or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def vless_client_uuids_csv_for_server(session: Session, server: Server) -> str:
    """
    Строка UUID через запятую для VPN_VLESS_CLIENT_UUIDS (legacy).
    Если нет ни одного активного пользователя — в конфиг попадает только UUID узла (fallback).
    """
    uuids = active_subscription_user_uuids(session)
    fallback = (server.vless_uuid or "").strip()
    if not uuids:
        if fallback:
            return fallback
        return ""
    return ",".join(uuids)


def vless_clients_b64_for_server(session: Session, server: Server) -> str:
    """
    Base64 JSON массива клиентов: id (uuid), email u{id}@vpn, flow, level 0.
    Для Stats API Xray нужен email на клиенте.
    """
    flow = (server.vless_flow or "xtls-rprx-vision").strip() or "xtls-rprx-vision"
    entries: list[dict[str, object]] = []
    for u in active_subscription_users(session):
        uid = (u.vless_uuid or "").strip()
        if not uid:
            continue
        entries.append(
            {
                "id": uid,
                "email": f"u{u.id}@vpn",
                "flow": flow,
                "level": 0,
            }
        )
    if not entries:
        fb = (server.vless_uuid or "").strip()
        if fb:
            # u0@vpn → в statsquery приходит uid=0, в БД нет User с id=0 — трафик не пишется.
            any_uid = session.scalar(select(User.id).order_by(User.id.asc()).limit(1))
            email = f"u{any_uid}@vpn" if any_uid is not None else "u0@vpn"
            entries.append(
                {
                    "id": fb,
                    "email": email,
                    "flow": flow,
                    "level": 0,
                }
            )
    raw = json.dumps(entries, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
