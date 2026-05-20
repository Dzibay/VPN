from datetime import date, datetime, timezone

from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_telegram_id",
            "telegram_id",
            unique=True,
            postgresql_where=text("telegram_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_properties: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Учётная роль: client — клиент; manager — рефералы; admin — полный админ (JWT role совпадает с типом, кроме client→user).
    account_role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'client'"),
        default="client",
    )
    subscription_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Персональный потолок трафика (up+down, байты). NULL — без лимита (обычно после оплаты).
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    referral_link_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("referral_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Момент создания записи пользователя (регистрация / создание админом); для старых строк может быть null.
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=_utc_now,
    )
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    vless_uuid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
