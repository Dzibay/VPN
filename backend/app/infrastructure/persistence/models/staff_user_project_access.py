"""Many-to-many staff_users ↔ projects.

Для ролей admin/manager — определяет к каким проектам есть доступ и в какой роли.
super_admin эту таблицу игнорирует (доступ ко всем проектам).
"""

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class StaffUserProjectAccess(Base):
    __tablename__ = "staff_user_project_access"

    staff_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("staff_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: ``admin`` | ``manager`` в контексте конкретного проекта.
    role: Mapped[str] = mapped_column(Text, nullable=False)
