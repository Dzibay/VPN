from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Server(Base):
    __tablename__ = "servers"
    __table_args__ = (UniqueConstraint("host", "port", name="uq_servers_host_port"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    country: Mapped[str] = mapped_column(Text, nullable=False, default="")
    load_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whitelist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provision_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provision_status: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    provision_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provision_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_kind: Mapped[str] = mapped_column(Text, nullable=False, default="vless")
    vless_uuid: Mapped[str] = mapped_column(Text, nullable=False)
    reality_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reality_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reality_short_id: Mapped[str] = mapped_column(Text, nullable=False)
    reality_dest: Mapped[str] = mapped_column(
        Text, nullable=False, default="www.amazon.com:443"
    )
    reality_server_names: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="www.amazon.com,amazon.com",
    )
    reality_fingerprint: Mapped[str] = mapped_column(
        Text, nullable=False, default="chrome"
    )
    reality_spider_x: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="/",
        doc="REALITY spiderX: HTTP-путь к ресурсу на dest (напр. / или /favicon.ico).",
    )
    vless_flow: Mapped[str] = mapped_column(
        Text, nullable=False, default="xtls-rprx-vision"
    )
    prometheus_instance: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_cap_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_cascade_ru_entry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cascade_next_server_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("servers.id", ondelete="SET NULL"),
        nullable=True,
    )
    cascade_egress_client_uuid: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True
    )
