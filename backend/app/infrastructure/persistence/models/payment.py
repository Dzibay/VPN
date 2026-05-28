from datetime import datetime
from decimal import Decimal

from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
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
    #: Полное тело webhook провайдера (Tribute ``{name,payload}``, ЮKassa ``{event,object}``); null для manual.
    provider_webhook: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
