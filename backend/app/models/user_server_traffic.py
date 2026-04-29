from datetime import date as date_type

from sqlalchemy import BigInteger, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserServerTraffic(Base):
    """Трафик пользователя на узле по календарным дням (UTC).

    За каждый день одна строка; при каждом сборе statsquery строка «сегодня»
    обновляется актуальными накопленными байтами (как раньше одна строка без даты).
    Исторические дни не меняются — можно строить графики по traffic_date.
    """

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
    traffic_date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    up_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    down_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    raw_up: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    raw_down: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
