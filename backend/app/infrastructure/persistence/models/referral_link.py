from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ReferralLink(Base):
    """Реферальный токен: владелец (пользователь или кампания) и счётчики конверсии."""

    __tablename__ = "referral_links"
    __table_args__ = (
        Index("uq_referral_links_project_token", "project_id", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Уникальность теперь per-project (см. __table_args__).
    token: Mapped[str] = mapped_column(Text, nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("referral_link_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    clicks_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    registrations_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    payments_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
