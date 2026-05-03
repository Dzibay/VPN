"""Формирование целей HTTP SD для Prometheus по активным серверам."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.persistence.models.server import Server


def node_exporter_targets(session: Session, settings: Settings) -> list[dict[str, Any]]:
    stmt = select(Server).where(Server.is_active.is_(True)).order_by(Server.id)
    servers = list(session.scalars(stmt).all())
    port = int(settings.provision_node_exporter_port)
    out: list[dict[str, Any]] = []
    for s in servers:
        inst = (s.prometheus_instance or "").strip()
        if not inst:
            inst = f"{s.host.strip()}:{port}"
        name = (s.name or "").strip()
        labels: dict[str, str] = {"server_id": str(s.id)}
        if name:
            labels["server_name"] = name
        out.append({"targets": [inst], "labels": labels})
    return out
