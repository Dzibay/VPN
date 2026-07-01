"""Мульти-проект: корневая таблица тенанта.

Определяет отдельный «бренд» — сайт на своём домене, свой Telegram-бот, платёжные
ключи, брендинг, юр. документы, реферальная политика. Один backend обслуживает N
проектов; резолвинг проекта — по Host (для публичных API), по slug в URL (для
webhook'ов), либо по X-Admin-Project (в админке).

Пул VPN-серверов общий на все проекты. Пользователи и связанные с ними сущности
(payments, tasks, subscription_devices и т.п.) изолированы через ``project_id``.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.infrastructure.database.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: Уникальный идентификатор проекта в URL/CLI/env (podorozhnik, project_b, …).
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: Человекочитаемое имя (для админки и селектора проекта).
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"), default=True
    )
    #: Основной домен сайта (podorozhnik-connect.ru). Резолвинг проекта по Host.
    primary_domain: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: Alias-домены (301 redirect на primary в edge). Тоже резолвятся в этот проект.
    extra_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"), default=list
    )

    # --- Telegram ---
    telegram_bot_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Shared secret bot ↔ API (заголовок X-Telegram-Bot-Secret). Уникален по всем проектам —
    #: используется как основной резолвер проекта из bot-запросов.
    telegram_bot_api_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Платёжные интеграции ---
    tribute_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    yookassa_shop_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    yookassa_secret_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    yookassa_return_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- SMTP override (nullable → fallback на глобальный settings.smtp_*) ---
    smtp_settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Реферальная политика (per-project override) ---
    referral_bonus_days_per_paid_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referral_fixed_first_payment_bonus_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referral_bonus_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Брендинг подписки (Happ) ---
    happ_provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Баннер об истечении подписки (payload для yaml подписки).
    subscription_sub_expire_banner: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: Info-баннер в подписке (payload для yaml).
    subscription_sub_info_banner: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    #: Минимальный набор брендинга для backend (frontend имеет свою сборку):
    #: ``brand_name`` — имя для YAML подписки и текстов бота.
    brand: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
