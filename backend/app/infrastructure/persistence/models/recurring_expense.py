from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class RecurringExpense(Base):
    """Ежемесячный шаблон расхода. В сводку разворачивается виртуально по месяцам диапазона."""

    __tablename__ = "recurring_expenses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("expense_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: День месяца для отображения даты списания (1..28).
    day_of_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    #: Первый месяц действия (любая дата, считается по началу месяца).
    start_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Последний месяц действия включительно; NULL — бессрочно.
    end_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
