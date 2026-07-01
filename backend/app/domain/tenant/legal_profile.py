"""Публичный профиль проекта для юридических документов на SPA."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.public_urls import (
    public_spa_base_url,
    support_telegram_public_url,
    telegram_bot_public_page_url,
)
from app.domain.tenant.project_context import get_current_project
from app.domain.tenant.project_trial import resolve_project_trial_settings


def _brand_legal_field(project, key: str) -> str | None:
    if project is None or not project.brand:
        return None
    legal = project.brand.get("legal")
    if not isinstance(legal, dict):
        return None
    raw = legal.get(key)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _clean_username(raw: str | None) -> str | None:
    if not raw:
        return None
    clean = str(raw).strip().lstrip("@")
    return clean or None


def _telegram_handle(username: str | None) -> str | None:
    if not username:
        return None
    clean = str(username).strip().lstrip("@")
    return f"@{clean}" if clean else None


@dataclass(frozen=True)
class ProjectLegalProfile:
    service_name: str
    site_url: str | None
    domain: str | None
    telegram_bot: str | None
    support_telegram: str | None
    support_email: str | None
    operator_name: str | None
    operator_inn: str | None
    dispute_jurisdiction: str | None
    effective_date: str | None
    trial_days_after_registration: int
    trial_extra_days_referral_registration: int
    trial_days_with_referral: int
    trial_traffic_limit_gib: int
    telegram_bot_page_url: str | None
    support_telegram_url: str | None


def build_project_legal_profile(settings: object) -> ProjectLegalProfile:
    """Собрать плейсхолдеры для юридических документов из текущего проекта запроса."""
    project = get_current_project()

    site_url = public_spa_base_url(settings, project)
    domain = None
    if project is not None and project.primary_domain:
        domain = str(project.primary_domain).strip().lower() or None
    elif site_url:
        try:
            from urllib.parse import urlparse

            domain = urlparse(site_url).hostname
        except Exception:
            domain = None

    service_name = None
    if project is not None:
        service_name = project.brand_name or (project.name or "").strip() or None
    if not service_name:
        service_name = "VPN"

    bot_username = _clean_username(project.telegram_bot_username if project else None)
    if not bot_username:
        bot_username = _clean_username(getattr(settings, "telegram_bot_username", None))

    support_username = _clean_username(project.support_telegram_username if project else None)
    if not support_username:
        support_username = _clean_username(getattr(settings, "support_telegram_username", None))

    telegram_bot = _telegram_handle(bot_username)
    support_telegram = _telegram_handle(support_username) or telegram_bot

    support_email = None
    if project is not None and project.support_email:
        support_email = str(project.support_email).strip() or None

    trial = resolve_project_trial_settings(settings, project=project)

    return ProjectLegalProfile(
        service_name=service_name,
        site_url=site_url,
        domain=domain,
        telegram_bot=telegram_bot,
        support_telegram=support_telegram,
        support_email=support_email,
        operator_name=_brand_legal_field(project, "operator_name"),
        operator_inn=_brand_legal_field(project, "operator_inn"),
        dispute_jurisdiction=_brand_legal_field(project, "dispute_jurisdiction"),
        effective_date=_brand_legal_field(project, "effective_date"),
        trial_days_after_registration=trial.trial_days_after_registration,
        trial_extra_days_referral_registration=trial.trial_extra_days_referral_registration,
        trial_days_with_referral=trial.trial_days_with_referral,
        trial_traffic_limit_gib=trial.trial_traffic_limit_gib,
        telegram_bot_page_url=telegram_bot_public_page_url(settings, project),
        support_telegram_url=support_telegram_public_url(settings, project),
    )
