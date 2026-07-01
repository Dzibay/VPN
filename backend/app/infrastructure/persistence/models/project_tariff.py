"""Тарифы проекта (per-provider). Заменяют backend/app/data/tribute_tariffs.json + yookassa_tariffs.json."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class ProjectTariff(Base):
    __tablename__ = "project_tariffs"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "months", name="uq_project_tariffs_prov_months"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: ``tribute`` | ``yookassa`` (CHECK на уровне БД).
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    #: 1 / 3 / 6 / 12. 0 — recurring / non-monthly (например Tribute subscription-плейн).
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Сумма в рублях (для YooKassa ровно так, для Tribute — как в кабинете).
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    #: Название тарифа для отображения ("1 мес", "3 мес", "Подписка").
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Готовая ссылка (для Tribute web/tg).
    external_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Telegram deep-link (например Tribute app startapp) для бота.
    external_tg_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Дополнительный ID продукта у провайдера (Tribute product/subscription id, если пригодится).
    external_product_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Внутренний тип тарифа (``single`` / ``recurring`` для Tribute).
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"), default=True
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
