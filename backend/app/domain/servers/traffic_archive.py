"""Сервер-заглушка id=0: хранение трафика с удалённых узлов в user_server_traffic."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.servers.reality_defaults import (
    REALITY_DEFAULT_DEST,
    REALITY_DEFAULT_FINGERPRINT,
    REALITY_DEFAULT_SERVER_NAMES,
    REALITY_DEFAULT_SPIDER_X,
    VLESS_DEFAULT_FLOW,
)
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic

TRAFFIC_ARCHIVE_SERVER_ID = 0
TRAFFIC_ARCHIVE_HOST = "__traffic_archive__"
TRAFFIC_ARCHIVE_PORT = 1
TRAFFIC_ARCHIVE_NAME = "Архив (удалённые узлы)"
TRAFFIC_ARCHIVE_VLESS_UUID = "00000000-0000-0000-0000-000000000001"
TRAFFIC_ARCHIVE_REALITY_SHORT_ID = "00000000"


async def ensure_traffic_archive_server(session: AsyncSession) -> Server:
    """Узел id=0 для накопления трафика после удаления реальных серверов."""
    existing = await session.get(Server, TRAFFIC_ARCHIVE_SERVER_ID)
    if existing is not None:
        return existing
    server = Server(
        id=TRAFFIC_ARCHIVE_SERVER_ID,
        name=TRAFFIC_ARCHIVE_NAME,
        host=TRAFFIC_ARCHIVE_HOST,
        port=TRAFFIC_ARCHIVE_PORT,
        country="",
        load_percent=0,
        is_active=False,
        whitelist=False,
        include_in_auto=False,
        is_hidden=True,
        provision_ready=False,
        provision_status="idle",
        proxy_kind="vless",
        vless_uuid=TRAFFIC_ARCHIVE_VLESS_UUID,
        reality_short_id=TRAFFIC_ARCHIVE_REALITY_SHORT_ID,
        reality_dest=REALITY_DEFAULT_DEST,
        reality_server_names=REALITY_DEFAULT_SERVER_NAMES,
        reality_fingerprint=REALITY_DEFAULT_FINGERPRINT,
        reality_spider_x=REALITY_DEFAULT_SPIDER_X,
        vless_flow=VLESS_DEFAULT_FLOW,
        is_cascade_ru_entry=False,
        cascade_next_server_id=None,
        cascade_egress_client_uuid=None,
    )
    await table_insert(session, server)
    await session.flush()
    return server


async def relocate_server_traffic_to_archive(
    session: AsyncSession,
    from_server_id: int,
) -> int:
    """Перенести все строки user_server_traffic с ``from_server_id`` на id=0.

    Для каждой пары (user_id, traffic_date) байты складываются в существующую
    строку архива или создаётся новая. Возвращает число перенесённых строк.
    """
    if from_server_id == TRAFFIC_ARCHIVE_SERVER_ID:
        return 0
    archive_id = TRAFFIC_ARCHIVE_SERVER_ID
    rows = (
        await session.scalars(
            select(UserServerTraffic).where(
                UserServerTraffic.server_id == from_server_id,
            ),
        )
    ).all()
    moved = 0
    for row in rows:
        pk = (row.user_id, archive_id, row.traffic_date)
        exist = await session.get(UserServerTraffic, pk)
        if exist is None:
            session.add(
                UserServerTraffic(
                    user_id=row.user_id,
                    server_id=archive_id,
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
        await session.delete(row)
        moved += 1
    if moved:
        await session.flush()
    return moved


def assert_deletable_server_id(server_id: int) -> None:
    if server_id == TRAFFIC_ARCHIVE_SERVER_ID:
        raise ConflictError("Сервер архива трафика (id=0) удалять нельзя")
