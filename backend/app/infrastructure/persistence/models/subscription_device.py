from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class SubscriptionDevice(Base):
    """Устройство/клиент, с которого запрашивали конфигурацию по /sub/{token}."""

    __tablename__ = "subscription_devices"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "fingerprint",
            name="uq_subscription_devices_user_fp",
        ),
        Index("idx_subscription_devices_user_updated_at", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Нормализованный ключ: hw из x-hwid или hdr:SHA256(заголовки)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)

    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Значение заголовка x-device-os при последнем запросе
    os: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Сырое значение заголовка x-hwid при последнем запросе
    hwid_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
