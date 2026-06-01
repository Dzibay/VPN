from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class ExpenseCategory(Base):
    """Категория расходов (для группировки P&L и цветов на графиках)."""

    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'#94a3b8'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
