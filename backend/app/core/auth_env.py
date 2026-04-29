"""Утилиты для авторизации по email."""


def normalize_email(email: str) -> str:
    return email.strip().lower()
