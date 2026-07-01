from datetime import date, datetime

from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_project_telegram_id",
            "project_id",
            "telegram_id",
            unique=True,
            postgresql_where=text("telegram_id IS NOT NULL"),
        ),
        Index(
            "uq_users_project_email",
            "project_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_users_project_token",
            "project_id",
            "token",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: Проект, к которому принадлежит пользователь. UNIQUE (project_id, telegram_id) /
    #: (project_id, email) — один и тот же человек может иметь отдельную учётку в разных проектах.
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    #: Индивидуальные условия начисления реферальных бонусов (см. app.constants REFERRAL_BONUS_*).
    referral_bonus_policy: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'default'"),
        default="default",
    )
    #: Переопределение суммы реферального бонуса на баланс (копейки); NULL — глобальный дефолт из Settings.
    referral_fixed_bonus_kopecks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Накопленный баланс пользователя (копейки); списание — отдельная задача.
    balance_kopecks: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    #: Момент создания записи пользователя (регистрация / создание админом); для старых строк может быть null.
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=utc_now,
    )
    #: Когда пользователь последний раз открывал чат поддержки (для бейджа непрочитанных).
    support_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    #: Когда подтверждён email (NULL — ожидает подтверждения после регистрации/привязки).
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    #: Токен подписки для URL /sub/{token}. Уникален глобально (для совместимости с существующими URL),
    #: плюс secondary индекс (project_id, token) для быстрого lookup внутри проекта.
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    #: VLESS UUID пользователя на всех узлах — уникален глобально (используется в конфиге xray).
    vless_uuid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
