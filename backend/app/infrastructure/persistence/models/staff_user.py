"""Персонал (отдельно от таблицы users).

Users теперь чисто клиентская таблица per-project. Staff (super_admin/admin/manager) живёт
в staff_users глобально; связь с проектами — через staff_user_project_access для admin/manager.
super_admin имеет доступ ко всем проектам и глобальным операциям (управление projects, staff_users).
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``super_admin`` | ``admin`` | ``manager``. super_admin — global; остальные — через staff_user_project_access.
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
