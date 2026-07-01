"""Per-project настройки тестового периода и лимита трафика."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, settings
from app.constants import (
    TRIAL_DAYS_AFTER_REGISTRATION,
    TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION,
    TRIAL_TRAFFIC_LIMIT_GIB,
)
from app.domain.tenant.project_context import ProjectContext, get_current_project


@dataclass(frozen=True, slots=True)
class ProjectTrialSettings:
    trial_days_after_registration: int
    trial_extra_days_referral_registration: int
    trial_traffic_limit_gib: int
    trial_traffic_limit_enabled: bool

    @property
    def trial_days_with_referral(self) -> int:
        return self.trial_days_after_registration + self.trial_extra_days_referral_registration


def resolve_project_trial_settings(
    cfg: Settings | None = None,
    *,
    project: ProjectContext | None = None,
) -> ProjectTrialSettings:
    """Настройки триала текущего (или явно переданного) проекта с fallback на env."""
    cfg = cfg or settings
    project = project if project is not None else get_current_project()

    trial_days = TRIAL_DAYS_AFTER_REGISTRATION
    if project is not None and project.trial_days_after_registration is not None:
        trial_days = int(project.trial_days_after_registration)

    referral_extra = TRIAL_EXTRA_DAYS_USER_REFERRAL_REGISTRATION
    if project is not None and project.trial_extra_days_referral_registration is not None:
        referral_extra = int(project.trial_extra_days_referral_registration)

    traffic_gib = int(cfg.trial_traffic_limit_gib)
    if project is not None and project.trial_traffic_limit_gib is not None:
        traffic_gib = int(project.trial_traffic_limit_gib)

    traffic_enabled = bool(cfg.trial_traffic_limit_enabled)
    if project is not None and project.trial_traffic_limit_enabled is not None:
        traffic_enabled = bool(project.trial_traffic_limit_enabled)

    return ProjectTrialSettings(
        trial_days_after_registration=max(0, trial_days),
        trial_extra_days_referral_registration=max(0, referral_extra),
        trial_traffic_limit_gib=max(1, traffic_gib),
        trial_traffic_limit_enabled=traffic_enabled,
    )
