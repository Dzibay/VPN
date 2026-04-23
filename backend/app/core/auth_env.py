"""Учётные данные администратора из окружения (без БД)."""

from __future__ import annotations

import secrets

from app.core.config import Settings


def normalize_email(email: str) -> str:
    return email.strip().lower()


def admin_email_normalized(settings: Settings) -> str:
    return normalize_email(str(settings.admin_email or ""))


def admin_password_configured(settings: Settings) -> bool:
    return bool((settings.admin_email or "").strip() and (settings.admin_password or "").strip())


def password_matches_admin(settings: Settings, provided: str) -> bool:
    expected = settings.admin_password or ""
    try:
        a = provided.encode("utf-8")
        b = expected.encode("utf-8")
    except Exception:
        return False
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)
