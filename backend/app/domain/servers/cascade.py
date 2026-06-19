"""Каскадная связка: РФ-вход + единственный внешний exit-узел.

Правила:

* запись с ``cascade_next_server_id`` обязательно должна быть «РФ-входом»
  (``is_cascade_ru_entry=True``);
* exit-узел не может сам быть РФ-входом и не может иметь собственного ``cascade_next``;
* пара (РФ-вход, exit) — одного уровня вложенности, цепочки запрещены.

При изменении cascade-поля на РФ-входе нужно прокачать sync Xray-клиентов на exit, чтобы
inbound на нём учитывал нового арендатора (``cascade_egress_client_uuid``).

Вход (РФ): ``vless``, ``vless_grpc``, ``vless_ws``, ``vless_xhttp``. Exit: те же три типа; магистраль
по ``proxy_kind`` exit (см. ``provision_cascade.sh``).
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BadRequestError
from app.domain.users.xray_sync_queue import ensure_sync_xray_clients_to_server_enqueued
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.servers.cascade")


async def validate_cascade_pair(
    session: AsyncSession,
    *,
    self_id: int | None,
    is_ru_entry: bool,
    cascade_next_id: int | None,
) -> None:
    """Проверить корректность пары РФ-вход → внешний exit.

    Бросает :class:`BadRequestError` при любом нарушении инвариантов каскада.
    """
    if cascade_next_id is None:
        return
    if not is_ru_entry:
        raise BadRequestError(
            "cascade_next_server_id задан: включите is_cascade_ru_entry (вход в каскаде) "
            "или сбросьте внешний id",
        )
    if self_id is not None and cascade_next_id == self_id:
        raise BadRequestError(
            "cascade_next_server_id не может совпадать с id этого сервера",
        )
    target = await session.get(Server, cascade_next_id)
    if target is None:
        raise BadRequestError(
            "cascade_next_server_id: внешний сервер не найден",
        )
    if target.is_cascade_ru_entry:
        raise BadRequestError(
            "Каскад: внешний узел — сервер с is_cascade_ru_entry=false; "
            "нельзя направлять на вход (РФ) другой пары",
        )
    if target.cascade_next_server_id is not None:
        raise BadRequestError(
            "Каскад: внешний узел не должен иметь собственного cascade_next (один уровень)",
        )
    ekind = (target.proxy_kind or "vless").strip().lower()
    if ekind not in ("vless", "vless_grpc", "vless_ws"):
        raise BadRequestError(
            "Каскад: внешний exit должен быть VLESS+REALITY, gRPC+TLS или WebSocket+TLS "
            f"(сейчас proxy_kind={ekind})",
        )


def merge_cascade_fields(
    server: Server,
    data: dict,
) -> tuple[bool, int | None]:
    """Свести фактические значения cascade-полей с пришедшим в PATCH-теле.

    Защёлкивает инвариант: либо ``is_ru_entry=False`` ⇒ ``next_id=None``, либо при заданном
    ``next_id`` входной флаг автоматически становится ``True``.
    """
    is_ru = server.is_cascade_ru_entry
    next_id = server.cascade_next_server_id
    if "is_cascade_ru_entry" in data:
        is_ru = bool(data["is_cascade_ru_entry"])
    if "cascade_next_server_id" in data:
        next_id = data["cascade_next_server_id"]
    if is_ru is False:
        next_id = None
    elif next_id is not None:
        is_ru = True
    return is_ru, next_id


async def try_enqueue_sync_xray_on_exit_for_cascade(
    session: AsyncSession, *exit_ids: int | None,
) -> None:
    """Поставить точечный sync Xray-клиентов на exit-узлы каскада.

    Принимает несколько exit-id (старый и новый при PATCH); пропускает ``None``, узлы без
    ``provision_ready`` и режим внешнего ``provision_command`` (там оркестрация другая).
    """
    need = {int(x) for x in exit_ids if x is not None}
    for eid in need:
        ex = await session.get(Server, eid)
        if ex is None or not ex.provision_ready:
            log.info(
                "cascade: пропуск sync Xray на exit id=%s (нет или provision_ready=false)",
                eid,
            )
            continue
        if (settings.provision_command or "").strip():
            continue
        try:
            ensure_sync_xray_clients_to_server_enqueued(eid)
        except RedisError as e:
            log.warning("cascade: не поставлена в очередь sync Xray на exit id=%s: %s", eid, e)
