from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class UserBalanceLedger(Base):
    __tablename__ = "user_balance_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    referee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    referee_payment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("NOW()"),
    )
