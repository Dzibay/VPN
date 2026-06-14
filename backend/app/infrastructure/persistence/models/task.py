from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.tasks.delivery_channel import TASK_DELIVERY_TELEGRAM
from app.core.time import utc_now
from app.infrastructure.database.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: Колонка в БД называется ``type`` (зарезервировано в Python — имя атрибута другое).
    task_type: Mapped[str] = mapped_column("type", Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    bonus_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Для ``notify_ref_pay`` с политикой balance: сумма бонуса в копейках.
    bonus_amount_kopecks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Для ``notify_ref_pay``: бонус уже зачислен на ``subscription_until`` (мгновенная политика).
    referral_bonus_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    #: Для ``notify_payment`` — бонус за досрочную оплату (не реферальный ``bonus_days``).
    early_payment_bonus_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Для ``notify_payment`` — число оплаченных месяцев (как в ``payments.months``).
    paid_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Куда доставлять оповещение: telegram — бот; website / email — другие потребители (ЛК, почта).
    delivery_channel: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TASK_DELIVERY_TELEGRAM,
        server_default="telegram",
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
