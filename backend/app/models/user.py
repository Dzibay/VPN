from datetime import date

from typing import Any

from sqlalchemy import BigInteger, Date, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


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
    subscription_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    vless_uuid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
