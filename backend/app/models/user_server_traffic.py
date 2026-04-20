from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserServerTraffic(Base):
    """Накопленный трафик пользователя на узле (байты с учётом сбросов счётчиков Xray)."""

    __tablename__ = "user_server_traffic"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    server_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("servers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    up_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    down_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    raw_up: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    raw_down: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
