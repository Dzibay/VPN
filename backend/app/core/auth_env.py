"""Утилиты для авторизации по email."""

_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def _canonicalize_gmail_local_part(local: str) -> str:
    base, _, _suffix = local.partition("+")
    return base


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized:
        return normalized
    local, domain = normalized.rsplit("@", 1)
    if domain in _GMAIL_DOMAINS:
        local = _canonicalize_gmail_local_part(local)
        domain = "gmail.com"
    return f"{local}@{domain}"
