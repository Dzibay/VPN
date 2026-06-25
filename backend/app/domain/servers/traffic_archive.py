"""Сервер-заглушка id=0: хранение трафика с удалённых узлов в user_server_traffic."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

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

ARCHIVE_REBUILD_ONE_TIME_MIGRATION = "traffic_archive_rebuild_from_raw_20260625"


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


async def _archive_carry_forward(
    session: AsyncSession,
    user_id: int,
    before_date: date,
) -> tuple[int, int, int, int]:
    """Последний снимок архива (id=0) строго до ``before_date`` — база для переноса."""
    prev = (
        await session.scalars(
            select(UserServerTraffic)
            .where(
                UserServerTraffic.user_id == user_id,
                UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID,
                UserServerTraffic.traffic_date < before_date,
            )
            .order_by(UserServerTraffic.traffic_date.desc())
            .limit(1),
        )
    ).first()
    if prev is None:
        return (0, 0, 0, 0)
    return (
        int(prev.up_bytes),
        int(prev.down_bytes),
        int(prev.raw_up),
        int(prev.raw_down),
    )


def _merge_axis_with_carry(
    carry: tuple[int, int, int, int],
    row: UserServerTraffic,
    prev_same_server: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Суммарный архивный снимок: уже архивированные узлы + накопление удаляемого."""
    return (
        carry[0] + int(row.up_bytes) - prev_same_server[0],
        carry[1] + int(row.down_bytes) - prev_same_server[1],
        carry[2] + int(row.raw_up) - prev_same_server[2],
        carry[3] + int(row.raw_down) - prev_same_server[3],
    )


async def relocate_server_traffic_to_archive(
    session: AsyncSession,
    from_server_id: int,
) -> int:
    """Перенести все строки user_server_traffic с ``from_server_id`` на id=0.

  Строки хранят накопленные байты на конкретном узле. В архиве на каждую дату
  должна лежать сумма по всем уже удалённым узлам; при новой дате без строки
  архива переносим ``carry + row - prev_same_server``, а при совпадении даты —
  прибавляем байты удаляемого узла к существующей строке.
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
    if not rows:
        return 0

    by_user: dict[int, list[UserServerTraffic]] = defaultdict(list)
    for row in rows:
        by_user[int(row.user_id)].append(row)

    moved = 0
    for user_id, user_rows in by_user.items():
        user_rows.sort(key=lambda r: r.traffic_date)
        prev_same_server = (0, 0, 0, 0)
        for row in user_rows:
            pk = (row.user_id, archive_id, row.traffic_date)
            exist = await session.get(UserServerTraffic, pk)
            if exist is None:
                carry = await _archive_carry_forward(session, user_id, row.traffic_date)
                up, down, raw_up, raw_down = _merge_axis_with_carry(
                    carry,
                    row,
                    prev_same_server,
                )
                session.add(
                    UserServerTraffic(
                        user_id=row.user_id,
                        server_id=archive_id,
                        traffic_date=row.traffic_date,
                        up_bytes=up,
                        down_bytes=down,
                        raw_up=raw_up,
                        raw_down=raw_down,
                    ),
                )
            else:
                exist.up_bytes += row.up_bytes
                exist.down_bytes += row.down_bytes
                exist.raw_up += row.raw_up
                exist.raw_down += row.raw_down
            prev_same_server = (
                int(row.up_bytes),
                int(row.down_bytes),
                int(row.raw_up),
                int(row.raw_down),
            )
            await session.delete(row)
            moved += 1
    await session.flush()
    return moved


def _merge_axis(total: int, raw_old: int, raw_new: int) -> tuple[int, int]:
    """Как в xray_stats_collect: накопление с учётом сброса счётчика Xray."""
    if raw_new >= raw_old:
        delta = raw_new - raw_old
    else:
        total += raw_old
        delta = raw_new
    return total + delta, raw_new


def _rebuild_archive_rows_from_raw(rows: list[UserServerTraffic]) -> int:
    """Пересчитать up_bytes/down_bytes из raw_up/raw_down (их не трогала ошибочная починка)."""
    if not rows:
        return 0
    has_raw = any(int(r.raw_up or 0) or int(r.raw_down or 0) for r in rows)
    if not has_raw:
        return 0

    updated = 0
    cum_up = 0
    cum_down = 0
    raw_up_prev = 0
    raw_down_prev = 0
    for row in rows:
        cum_up, raw_up_prev = _merge_axis(cum_up, raw_up_prev, int(row.raw_up or 0))
        cum_down, raw_down_prev = _merge_axis(cum_down, raw_down_prev, int(row.raw_down or 0))
        new_up = int(cum_up)
        new_down = int(cum_down)
        if int(row.up_bytes) != new_up or int(row.down_bytes) != new_down:
            row.up_bytes = new_up
            row.down_bytes = new_down
            updated += 1
    return updated


def rebuild_inflated_traffic_archive_sync() -> dict[str, int]:
    """Одноразовый пересчёт архива (server_id=0): raw → cumulative, затем forward-fill.

    Возвращает счётчики для лога: users, rows_rebuilt, rows_forward_filled.
    """
    from app.infrastructure.database.session import SessionLocal

    stats = {"users": 0, "rows_rebuilt": 0, "rows_forward_filled": 0}
    with SessionLocal() as session:
        user_ids = list(
            session.scalars(
                select(UserServerTraffic.user_id)
                .where(UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID)
                .distinct()
                .order_by(UserServerTraffic.user_id.asc()),
            ).all(),
        )
        stats["users"] = len(user_ids)
        for user_id in user_ids:
            rows = list(
                session.scalars(
                    select(UserServerTraffic)
                    .where(
                        UserServerTraffic.user_id == user_id,
                        UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID,
                    )
                    .order_by(UserServerTraffic.traffic_date.asc()),
                ).all(),
            )
            stats["rows_rebuilt"] += _rebuild_archive_rows_from_raw(rows)

        # forward-fill после пересчёта (на случай оставшихся провалов)
        for user_id in user_ids:
            prev_total = 0
            rows = list(
                session.scalars(
                    select(UserServerTraffic)
                    .where(
                        UserServerTraffic.user_id == user_id,
                        UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID,
                    )
                    .order_by(UserServerTraffic.traffic_date.asc()),
                ).all(),
            )
            for row in rows:
                total = int(row.up_bytes) + int(row.down_bytes)
                if total < prev_total:
                    if prev_total > 0 and total > 0:
                        up_share = int(row.up_bytes) / total
                        row.up_bytes = int(round(prev_total * up_share))
                        row.down_bytes = prev_total - int(row.up_bytes)
                    else:
                        row.up_bytes = 0
                        row.down_bytes = prev_total
                    stats["rows_forward_filled"] += 1
                else:
                    prev_total = total

        session.commit()
    return stats


async def rebuild_inflated_traffic_archive(session: AsyncSession) -> dict[str, int]:
    """Async-обёртка: пересчёт архива в текущей сессии."""
    user_ids = (
        await session.scalars(
            select(UserServerTraffic.user_id)
            .where(UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID)
            .distinct()
            .order_by(UserServerTraffic.user_id.asc()),
        )
    ).all()
    stats = {"users": len(user_ids), "rows_rebuilt": 0, "rows_forward_filled": 0}
    for user_id in user_ids:
        rows = list(
            (
                await session.scalars(
                    select(UserServerTraffic)
                    .where(
                        UserServerTraffic.user_id == user_id,
                        UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID,
                    )
                    .order_by(UserServerTraffic.traffic_date.asc()),
                )
            ).all(),
        )
        stats["rows_rebuilt"] += _rebuild_archive_rows_from_raw(rows)
    stats["rows_forward_filled"] = await repair_traffic_archive_totals(session)
    return stats


async def repair_traffic_archive_totals(session: AsyncSession) -> int:
    """Выровнять накопительный ряд архива (id=0): cumulative не должен убывать.

    Старый перенос без carry-forward иногда записывал в архив только cumulative
    удалённого узла (меньше предыдущего архивного снимка). Здесь не «добавляем»
    cur к prev (это каскадно раздувает график), а forward-fill: total := prev_total.
    """
    user_ids = (
        await session.scalars(
            select(UserServerTraffic.user_id)
            .where(UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID)
            .distinct()
            .order_by(UserServerTraffic.user_id.asc()),
        )
    ).all()
    fixed = 0
    for user_id in user_ids:
        rows = (
            await session.scalars(
                select(UserServerTraffic)
                .where(
                    UserServerTraffic.user_id == user_id,
                    UserServerTraffic.server_id == TRAFFIC_ARCHIVE_SERVER_ID,
                )
                .order_by(UserServerTraffic.traffic_date.asc()),
            )
        ).all()
        prev_total = 0
        for row in rows:
            total = int(row.up_bytes) + int(row.down_bytes)
            if total < prev_total:
                if prev_total > 0 and total > 0:
                    up_share = int(row.up_bytes) / total
                    row.up_bytes = int(round(prev_total * up_share))
                    row.down_bytes = prev_total - int(row.up_bytes)
                else:
                    row.up_bytes = 0
                    row.down_bytes = prev_total
                fixed += 1
            else:
                prev_total = total
    if fixed:
        await session.flush()
    return fixed


def assert_deletable_server_id(server_id: int) -> None:
    if server_id == TRAFFIC_ARCHIVE_SERVER_ID:
        raise ConflictError("Сервер архива трафика (id=0) удалять нельзя")
