from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'manual'"),
    )
    #: ``subscription`` (Tribute recurring) | ``one_time`` (Tribute digital product).
    payment_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'subscription'"),
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
