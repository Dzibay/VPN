"""
Публичный эндпоинт подписки (без префикса /api — стабильные ссылки /sub/{token}).
"""

from __future__ import annotations

import base64
import logging
from datetime import date
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.database.operations import table_select_one
from app.models.server import Server
from app.models.user import User
from app.schemas.users import SubscriptionPayload

router = APIRouter(tags=["subscription"])
log = logging.getLogger("app.subscription")


def _user_subscription_active(user: User) -> bool:
    if user.subscription_until is None:
        return True
    return user.subscription_until >= date.today()


def _subscription_server_rows(session: Session) -> list[Server]:
    stmt = (
        select(Server)
        .where(
            Server.is_active.is_(True),
            Server.provision_ready.is_(True),
            Server.reality_public_key.isnot(None),
            Server.reality_public_key != "",
        )
        .order_by(Server.load_percent.asc(), Server.id.asc())
    )
    return list(session.scalars(stmt).all())


def _primary_sni(server_names: str, dest: str) -> str:
    for part in (server_names or "").split(","):
        host = part.strip().split(":", 1)[0].strip()
        if host:
            return host
    d = (dest or "").strip()
    if not d:
        return ""
    return d.rsplit(":", 1)[0] if ":" in d else d


def _vless_reality_share_uri(s: Server) -> str | None:
    """Ссылка vless:// в формате, совместимом с Xray / v2rayNG (tcp + REALITY + flow)."""
    pbk = (s.reality_public_key or "").strip()
    if not pbk or "(" in pbk:
        log.warning("Пропуск узла id=%s в подписке: некорректный reality_public_key", s.id)
        return None
    sid = (s.reality_short_id or "").strip()
    if not sid:
        log.warning("Пропуск узла id=%s: пустой reality_short_id", s.id)
        return None
    flow = (s.vless_flow or "").strip() or "xtls-rprx-vision"
    fp = (s.reality_fingerprint or "").strip() or "chrome"
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    if not sni:
        log.warning("Пропуск узла id=%s: не удалось вывести SNI", s.id)
        return None

    params = {
        "encryption": "none",
        "security": "reality",
        "type": "tcp",
        "headerType": "none",
        "flow": flow,
        "sni": sni,
        "fp": fp,
        "pbk": pbk,
        "sid": sid,
    }
    query = urlencode(params, quote_via=quote, safe="")
    remark = (s.name or s.country or s.host or "node").strip()
    fragment = quote(remark, safe="")
    uuid = (s.vless_uuid or "").strip()
    host = (s.host or "").strip()
    if not uuid or not host:
        return None
    return f"vless://{uuid}@{host}:{int(s.port)}?{query}#{fragment}"


def _server_to_subscription_dict(s: Server) -> dict[str, Any]:
    """Структурированные поля + удобные для клиента имена (sni, pbk, sid)."""
    sni = _primary_sni(s.reality_server_names, s.reality_dest)
    return {
        "id": s.id,
        "name": s.name or s.host,
        "country": s.country,
        "address": s.host,
        "port": s.port,
        "uuid": s.vless_uuid,
        "flow": s.vless_flow,
        "encryption": "none",
        "network": "tcp",
        "security": "reality",
        "sni": sni,
        "fingerprint": s.reality_fingerprint,
        "public_key": s.reality_public_key,
        "short_id": s.reality_short_id,
        "dest": s.reality_dest,
        "server_names": s.reality_server_names,
        # прежние имена полей — для совместимости
        "host": s.host,
        "vless_uuid": s.vless_uuid,
        "vless_flow": s.vless_flow,
        "reality_public_key": s.reality_public_key,
        "reality_short_id": s.reality_short_id,
        "reality_dest": s.reality_dest,
        "reality_server_names": s.reality_server_names,
        "reality_fingerprint": s.reality_fingerprint,
    }


def _build_payload_for_rows(user: User, rows: list[Server]) -> SubscriptionPayload:
    servers_out: list[dict[str, Any]] = []
    uris: list[str] = []
    for s in rows:
        servers_out.append(_server_to_subscription_dict(s))
        uri = _vless_reality_share_uri(s)
        if uri:
            uris.append(uri)
    raw = "\n".join(uris) + ("\n" if uris else "")
    b64 = base64.standard_b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
    return SubscriptionPayload(
        valid_until=user.subscription_until,
        subscription_active=True,
        servers=servers_out,
        vless_uris=uris,
        subscription_base64=b64,
    )


@router.get(
    "/sub/{token}",
    response_model=SubscriptionPayload,
    summary="Подписка (JSON): узлы, vless:// и Base64 для импорта",
)
async def subscription_by_token(token: str, session: SessionDep) -> SubscriptionPayload:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    if not _user_subscription_active(user):
        return SubscriptionPayload(
            valid_until=user.subscription_until,
            subscription_active=False,
            servers=[],
            vless_uris=[],
            subscription_base64="",
        )

    rows = _subscription_server_rows(session)
    return _build_payload_for_rows(user, rows)


@router.get(
    "/sub/{token}/raw",
    summary="Тело подписки как text/plain (только Base64) — для v2rayNG, Nekoray и др.",
    response_class=Response,
)
async def subscription_base64_raw(token: str, session: SessionDep) -> Response:
    user = table_select_one(session, User, filters={"token": token})
    if user is None:
        raise HTTPException(status_code=404, detail="Неизвестный токен")

    if not _user_subscription_active(user):
        return Response(content="", media_type="text/plain; charset=utf-8")

    payload = _build_payload_for_rows(user, _subscription_server_rows(session))
    return Response(
        content=payload.subscription_base64,
        media_type="text/plain; charset=utf-8",
    )
