from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
