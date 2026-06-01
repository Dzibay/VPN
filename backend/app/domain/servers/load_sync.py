"""Подтягивание текущей нагрузки узлов из Prometheus.

Запросы к Prometheus (httpx) и запись результата выполняются синхронно поверх sync-сессии,
поэтому вся работа уходит в threadpool и не блокирует event loop API.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models.servers import (
    ServerLoadSyncItemRead,
    ServerLoadSyncResultRead,
)
from app.infrastructure.database.blocking import run_blocking_with_session
from app.infrastructure.prometheus.server_load_sync import (
    sync_all_servers_load_from_prometheus,
)


def _sync_load_from_prometheus_blocking(db: Session, hours: int) -> ServerLoadSyncResultRead:
    """Синхронная реализация: крутит httpx (запросы Prometheus) поверх sync-сессии.

    Вызывать только из ``run_blocking_with_session`` — внутри нет ``await`` точек.
    """
    rep = sync_all_servers_load_from_prometheus(db, hours=hours)
    return ServerLoadSyncResultRead(
        hours=rep.hours,
        items=[
            ServerLoadSyncItemRead(
                server_id=i.server_id,
                host=i.host,
                ok=i.ok,
                load_percent=i.load_percent,
                detail=i.detail,
            )
            for i in rep.items
        ],
        updated=sum(1 for i in rep.items if i.ok),
        failed=sum(1 for i in rep.items if not i.ok),
    )


async def sync_load_from_prometheus_result(hours: int) -> ServerLoadSyncResultRead:
    """Подтянуть текущую нагрузку узлов из Prometheus (среднее за последние ``hours`` часов).

    Внутри: sync httpx + sync SQLAlchemy (см. ``infrastructure.prometheus.server_load_sync``);
    обёрнуто в threadpool, чтобы не блокировать event loop API на время запросов.
    """
    return await run_blocking_with_session(_sync_load_from_prometheus_blocking, hours)
