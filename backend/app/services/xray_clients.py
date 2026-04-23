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


def cascade_egress_uuids_for_exit_server(session: Session, exit_server: Server) -> list[str]:
    """
    UUID клиентов с РФ-входов, направленных на этот сервер как exit.
    """
    stmt = select(Server).where(
        Server.cascade_next_server_id == exit_server.id,
        Server.cascade_egress_client_uuid.isnot(None),
    )
    out: list[str] = []
    for s in session.scalars(stmt).all():
        u = (s.cascade_egress_client_uuid or "").strip()
        if u and u not in out:
            out.append(u)
    return out


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
    uuids = list(active_subscription_user_uuids(session))
    seen = set(uuids)
    for c in cascade_egress_uuids_for_exit_server(session, server):
        if c not in seen:
            seen.add(c)
            uuids.append(c)
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
    seen_ids: set[str] = set()
    for u in active_subscription_users(session):
        uid = (u.vless_uuid or "").strip()
        if not uid:
            continue
        if uid in seen_ids:
            continue
        seen_ids.add(uid)
        entries.append(
            {
                "id": uid,
                "email": f"u{u.id}@vpn",
                "flow": flow,
                "level": 0,
            }
        )
    for ru in session.scalars(
        select(Server).where(
            Server.cascade_next_server_id == server.id,
            Server.cascade_egress_client_uuid.isnot(None),
        )
    ).all():
        cuid = (ru.cascade_egress_client_uuid or "").strip()
        if not cuid or cuid in seen_ids:
            continue
        seen_ids.add(cuid)
        entries.append(
            {
                "id": cuid,
                "email": f"ru_entry{ru.id}@cascade",
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
