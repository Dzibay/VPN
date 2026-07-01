"""Одноразовый перенос legacy глобальных настроек Подорожника в строку projects(id=1).

Раньше все per-project поля были в env / Settings (SITE_ADDRESS, TELEGRAM_BOT_*, TRIBUTE_*
и т.п.). После миграции они переехали в таблицу ``projects``, но чтобы не переписывать
все места вручную и не терять существующую конфигурацию — один раз при старте API
берём поля из ``settings`` и записываем в проект id=1 (только если они там пусты).

Это идемпотентно и safe: перезаписываем только NULL / пустые строки. Ручное изменение
проекта через админку не пострадает.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.infrastructure.persistence.models.project import Project
from app.infrastructure.persistence.models.project_tariff import ProjectTariff

log = logging.getLogger(__name__)

_LEGACY_TRIBUTE_JSON = Path(__file__).resolve().parents[2] / "data" / "tribute_tariffs.json"
_LEGACY_YOOKASSA_JSON = Path(__file__).resolve().parents[2] / "data" / "yookassa_tariffs.json"


def _domain_from_site_address(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if not s:
        return None
    if "://" in s:
        s = s.split("://", 1)[1]
    if "/" in s:
        s = s.split("/", 1)[0]
    if ":" in s:
        s = s.split(":", 1)[0]
    return s or None


async def sync_legacy_project_settings(session: AsyncSession, settings: Settings) -> None:
    """Заполняет пустые поля projects(id=1) из глобальных settings (env)."""
    project = (
        await session.execute(select(Project).where(Project.id == 1))
    ).scalars().first()
    if project is None:
        return

    patch: dict[str, object] = {}

    # primary_domain / extra_domains — обновляем ТОЛЬКО если primary_domain пустой или дефолтный.
    primary = _domain_from_site_address(settings.site_address)
    if primary and (not project.primary_domain or project.primary_domain == "podorozhnik-connect.ru"):
        patch["primary_domain"] = primary

    extras: list[str] = []
    for raw in settings.site_extra_addresses or []:
        d = _domain_from_site_address(raw)
        if d and d != primary and d not in extras:
            extras.append(d)
    if extras and not (project.extra_domains or []):
        patch["extra_domains"] = extras

    # Простой перенос: если поле в projects пусто, копируем из settings.
    single_map = [
        ("telegram_bot_username", settings.telegram_bot_username),
        ("telegram_bot_api_secret", settings.telegram_bot_api_secret),
        ("support_telegram_username", settings.support_telegram_username),
        ("tribute_api_key", settings.tribute_api_key),
        ("yookassa_shop_id", settings.yookassa_shop_id),
        ("yookassa_secret_key", settings.yookassa_secret_key),
        ("yookassa_return_url", settings.yookassa_return_url),
        ("happ_provider_id", settings.happ_provider_id),
    ]
    for column, value in single_map:
        current = getattr(project, column, None)
        if not current and value:
            patch[column] = value.strip() if isinstance(value, str) else value

    # Реферальные политики: числа.
    if project.referral_bonus_days_per_paid_month is None:
        patch["referral_bonus_days_per_paid_month"] = settings.referral_bonus_days_per_paid_month
    if project.referral_fixed_first_payment_bonus_rub is None:
        patch["referral_fixed_first_payment_bonus_rub"] = settings.referral_fixed_first_payment_bonus_rub

    from app.constants import (
        TRIAL_DAYS_AFTER_REGISTRATION,
        TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION,
        TRIAL_TRAFFIC_LIMIT_GIB,
    )

    if project.trial_days_after_registration is None:
        patch["trial_days_after_registration"] = TRIAL_DAYS_AFTER_REGISTRATION
    if project.trial_extra_days_referral_registration is None:
        patch["trial_extra_days_referral_registration"] = TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION
    if project.trial_traffic_limit_gib is None:
        patch["trial_traffic_limit_gib"] = int(settings.trial_traffic_limit_gib or TRIAL_TRAFFIC_LIMIT_GIB)
    if project.trial_traffic_limit_enabled is None:
        patch["trial_traffic_limit_enabled"] = bool(settings.trial_traffic_limit_enabled)

    if not project.brand:
        patch["brand"] = {"brand_name": "🍃 Подорожник VPN"}

    if patch:
        await session.execute(update(Project).where(Project.id == 1).values(**patch))
        await session.commit()
        log.info("projects(id=1): перенесено %d legacy-полей из env", len(patch))

    # Тарифы: если ещё не наполнены — заинсёртить из JSON-файлов.
    tariffs_count = (
        await session.execute(
            select(ProjectTariff.id).where(ProjectTariff.project_id == 1).limit(1)
        )
    ).first()
    if tariffs_count is None:
        await _seed_tariffs_from_json(session)


async def _seed_tariffs_from_json(session: AsyncSession) -> None:
    """Читает legacy tribute_tariffs.json + yookassa_tariffs.json и создаёт строки в project_tariffs."""
    inserted = 0
    try:
        tribute_data = json.loads(_LEGACY_TRIBUTE_JSON.read_text(encoding="utf-8"))
    except OSError:
        tribute_data = {"tariffs": []}
    for idx, t in enumerate(tribute_data.get("tariffs", []) or []):
        months = t.get("months")
        price = t.get("price")
        session.add(
            ProjectTariff(
                project_id=1,
                provider="tribute",
                months=int(months) if months is not None else 0,
                amount=int(price) if price is not None else 0,
                name=t.get("name"),
                external_link=t.get("web_link") or t.get("tg_link"),
                kind=t.get("type"),
                sort_order=(idx + 1) * 10,
            )
        )
        inserted += 1

    try:
        yookassa_data = json.loads(_LEGACY_YOOKASSA_JSON.read_text(encoding="utf-8"))
    except OSError:
        yookassa_data = {"tariffs": []}
    for idx, t in enumerate(yookassa_data.get("tariffs", []) or []):
        session.add(
            ProjectTariff(
                project_id=1,
                provider="yookassa",
                months=int(t.get("months") or 0),
                amount=int(t.get("price") or 0),
                name=t.get("name"),
                kind="single",
                sort_order=(idx + 1) * 10,
            )
        )
        inserted += 1

    if inserted:
        try:
            await session.commit()
            log.info("Сиды project_tariffs для project_id=1: %d строк", inserted)
        except Exception:
            await session.rollback()
            log.exception("Не удалось засидить project_tariffs")
