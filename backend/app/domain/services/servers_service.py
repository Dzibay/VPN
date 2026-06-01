"""Управление серверами: CRUD-операции и сборка доменных подмодулей в единый фасад.

Тяжёлые, самостоятельные блоки вынесены в пакет :mod:`app.domain.servers`, чтобы этот
модуль остался читаемым CRUD-ядром:

* очередь установки/sync Xray — :mod:`app.domain.servers.provisioning`,
* доступность узлов (Redis-история) — :mod:`app.domain.servers.reachability`,
* нагрузка из Prometheus — :mod:`app.domain.servers.load_sync`,
* каскад/REALITY/архив трафика — :mod:`app.domain.servers.{cascade,reality_defaults,traffic_archive}`.

Функции подмодулей реэкспортируются ниже, поэтому внешний код продолжает импортировать их
из ``app.domain.services.servers_service`` без изменений.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.exceptions import ConflictError, NotFoundError
from app.domain.models.servers import (
    ServerCreate,
    ServersCountResponse,
    ServerUpdate,
)
from app.domain.servers.cascade import (
    merge_cascade_fields,
    try_enqueue_sync_xray_on_exit_for_cascade,
    validate_cascade_pair,
)
from app.domain.servers.load_sync import sync_load_from_prometheus_result
from app.domain.servers.provisioning import (
    enqueue_component_install,
    enqueue_full_provision,
    enqueue_server_reconcile,
    enqueue_sync_xray_all,
    enqueue_sync_xray_one,
    reset_server_provision,
)
from app.domain.servers.reachability import (
    server_reachability_history,
    servers_reachability_summary,
    tcp_probes_payload,
)
from app.domain.servers.reality_defaults import reality_defaults_for_create
from app.domain.servers.traffic_archive import (
    TRAFFIC_ARCHIVE_SERVER_ID,
    assert_deletable_server_id,
    ensure_traffic_archive_server,
    relocate_server_traffic_to_archive,
)
from app.infrastructure.cache import get_redis
from app.infrastructure.cache.server_reachability_store import (
    delete_server_reachability_key,
)
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.servers_service")

__all__ = [
    "servers_count",
    "list_servers",
    "create_server",
    "patch_server",
    "delete_server",
    # Реэкспорт доменных подмодулей (обратная совместимость импортов).
    "sync_load_from_prometheus_result",
    "tcp_probes_payload",
    "servers_reachability_summary",
    "server_reachability_history",
    "enqueue_sync_xray_all",
    "enqueue_sync_xray_one",
    "enqueue_full_provision",
    "reset_server_provision",
    "enqueue_server_reconcile",
    "enqueue_component_install",
]

_CASCADE_ENTRY_KINDS = frozenset({"vless", "vless_grpc", "vless_ws"})


def _assert_cascade_proxy_allowed(
    proxy_kind: str,
    *,
    is_ru_entry: bool,
    cascade_next_id: int | None,
) -> None:
    if not is_ru_entry and cascade_next_id is None:
        return
    pk = (proxy_kind or "vless").strip().lower()
    if pk == "hysteria2":
        raise ConflictError("Hysteria2 не поддерживает каскад")
    if is_ru_entry and cascade_next_id is not None and pk not in _CASCADE_ENTRY_KINDS:
        raise ConflictError(
            "Вход каскада: VLESS+REALITY, gRPC+TLS или WebSocket+TLS",
        )


async def servers_count(session: AsyncSession) -> ServersCountResponse:
    """Общее число записей в таблице ``servers`` (без служебного архива id=0)."""
    total = await session.scalar(
        select(func.count())
        .select_from(Server)
        .where(Server.id != TRAFFIC_ARCHIVE_SERVER_ID),
    )
    return ServersCountResponse(servers_count=int(total or 0))


async def list_servers(session: AsyncSession) -> list[Server]:
    """Список всех серверов; новейшие первыми (для админки)."""
    stmt = (
        select(Server)
        .where(Server.id != TRAFFIC_ARCHIVE_SERVER_ID)
        .order_by(Server.id.desc())
    )
    return list((await session.scalars(stmt)).all())


async def create_server(
    session: AsyncSession, body: ServerCreate, cfg: Settings | None = None,
) -> Server:
    """Создать запись сервера; недостающие REALITY/VLESS-поля заполняются дефолтами."""
    cfg = cfg or settings
    defaults = reality_defaults_for_create(body)
    is_ru = bool(body.is_cascade_ru_entry)
    cnext = body.cascade_next_server_id
    if cnext is not None:
        is_ru = True
    elif not is_ru:
        cnext = None
    _assert_cascade_proxy_allowed(body.proxy_kind, is_ru_entry=is_ru, cascade_next_id=cnext)
    await validate_cascade_pair(session, self_id=None, is_ru_entry=is_ru, cascade_next_id=cnext)
    cascade_egress_uuid: str | None = str(uuid_lib.uuid4()) if cnext else None
    server = Server(
        name=body.name,
        host=body.host,
        port=body.port,
        country=body.country,
        load_percent=body.load_percent,
        is_active=body.is_active,
        whitelist=body.whitelist,
        include_in_auto=body.include_in_auto,
        is_hidden=body.is_hidden,
        prometheus_instance=body.prometheus_instance,
        network_cap_mbps=body.network_cap_mbps,
        is_cascade_ru_entry=is_ru,
        cascade_next_server_id=cnext,
        cascade_egress_client_uuid=cascade_egress_uuid,
        proxy_kind=body.proxy_kind,
        **defaults,
    )
    try:
        await table_insert(session, server)
    except IntegrityError as e:
        log.warning("create_server conflict: %s", e)
        raise ConflictError(
            "Сервер с таким host и port уже существует",
        ) from e
    await try_enqueue_sync_xray_on_exit_for_cascade(session, cnext)
    return server


async def patch_server(session: AsyncSession, server_id: int, body: ServerUpdate) -> Server:
    """Частичное обновление сервера; cascade-поля валидируются совместно.

    Замена ``reality_private_key`` обнуляет публичный ключ — он будет пересчитан воркером.
    Изменение cascade-связки порождает sync Xray на старом и новом exit-узлах.
    """
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return server
    if data.get("reality_spider_x") is None and "reality_spider_x" in data:
        data["reality_spider_x"] = "/"
    priv_in = data.get("reality_private_key")
    if priv_in:
        new_priv = str(priv_in).strip()
        old_priv = (server.reality_private_key or "").strip()
        if new_priv != old_priv:
            server.reality_public_key = None
    if data.get("proxy_kind") in ("hysteria2", "vless_grpc", "vless_ws"):
        data["reality_public_key"] = None
    cascade_touched = False
    old_cnext: int | None = None
    if "is_cascade_ru_entry" in data or "cascade_next_server_id" in data:
        cascade_touched = True
        old_cnext = server.cascade_next_server_id
        old_cuuid = server.cascade_egress_client_uuid
        is_ru, cnext = merge_cascade_fields(server, data)
        await validate_cascade_pair(
            session,
            self_id=server_id,
            is_ru_entry=is_ru,
            cascade_next_id=cnext,
        )
        data["is_cascade_ru_entry"] = is_ru
        data["cascade_next_server_id"] = cnext
        if cnext is None:
            data["cascade_egress_client_uuid"] = None
        elif cnext != old_cnext or not (str(old_cuuid or "").strip()):
            data["cascade_egress_client_uuid"] = str(uuid_lib.uuid4())
    final_proxy = data.get("proxy_kind", server.proxy_kind or "vless")
    final_is_ru = bool(data.get("is_cascade_ru_entry", server.is_cascade_ru_entry))
    final_cnext = data.get("cascade_next_server_id", server.cascade_next_server_id)
    _assert_cascade_proxy_allowed(
        str(final_proxy),
        is_ru_entry=final_is_ru,
        cascade_next_id=final_cnext,
    )
    for key, value in data.items():
        setattr(server, key, value)
    await session.flush()
    if cascade_touched:
        await try_enqueue_sync_xray_on_exit_for_cascade(
            session,
            old_cnext,
            server.cascade_next_server_id,
        )
    return server


async def delete_server(session: AsyncSession, server_id: int) -> None:
    """Удалить запись сервера; трафик пользователей переносится на служебный узел id=0."""
    assert_deletable_server_id(server_id)
    server = await session.get(Server, server_id)
    if server is None:
        raise NotFoundError("Сервер не найден")
    await ensure_traffic_archive_server(session)
    moved = await relocate_server_traffic_to_archive(session, server_id)
    if moved:
        log.info(
            "delete_server: перенесено %s строк user_server_traffic server_id=%s → id=0",
            moved,
            server_id,
        )
    await session.delete(server)
    await session.flush()
    delete_server_reachability_key(get_redis(), server_id)
