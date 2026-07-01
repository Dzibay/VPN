from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class CashAccount(Base):
    """Место хранения денег: расчетник, PSP, наличные или внутренний счет."""

    __tablename__ = "cash_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'bank'"))
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'RUB'"))
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    opened_on: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    #: FK теперь на staff_users.
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True)


class CashTransaction(Base):
    """Ручные кассовые операции, которые не являются платежом/расходом/возвратом."""

    __tablename__ = "cash_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cash_accounts.id", ondelete="RESTRICT"), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'adjustment'"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True)


class Payable(Base):
    """Долг организации перед человеком/подрядчиком."""

    __tablename__ = "payables"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    counterparty_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    source_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    expense_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True)


class Refund(Base):
    """Возврат клиенту как финансовая корректировка платежа."""

    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cash_accounts.id", ondelete="SET NULL"), nullable=True)
    refunded_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'succeeded'"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True)


class ProfitWithdrawal(Base):
    """Вывод прибыли владельцу: cash-out, но не операционный расход P&L."""

    __tablename__ = "profit_withdrawals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cash_accounts.id", ondelete="SET NULL"), nullable=True)
    withdrawn_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recipient_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'succeeded'"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True)
