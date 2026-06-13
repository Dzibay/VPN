"""Общие правила валидации email/пароля для регистрации и привязки сайта.

Сообщения об ошибках совпадают с ``frontend/src/auth/credentialsValidation.js``.
"""

from __future__ import annotations

from app.core.exceptions import BadRequestError

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BCRYPT_BYTES = 72

PASSWORDS_MISMATCH_MSG = "Пароли не совпадают"
PASSWORD_TOO_SHORT_MSG = f"Пароль должен содержать не менее {PASSWORD_MIN_LENGTH} символов"
PASSWORD_TOO_LONG_MSG = "Пароль слишком длинный для системы входа"


def validate_new_site_password(password: str) -> None:
    """Новый пароль для сайта: длина в символах и лимит bcrypt в байтах UTF-8."""
    plain = str(password)
    if len(plain) < PASSWORD_MIN_LENGTH:
        raise BadRequestError(PASSWORD_TOO_SHORT_MSG)
    if len(plain.encode("utf-8")) > PASSWORD_MAX_BCRYPT_BYTES:
        raise BadRequestError(PASSWORD_TOO_LONG_MSG)


def validate_password_confirm(password: str, password_confirm: str | None) -> None:
    if password_confirm is None or str(password_confirm) != str(password):
        raise BadRequestError(PASSWORDS_MISMATCH_MSG)


def validate_new_site_password_with_confirm(
    password: str,
    password_confirm: str | None,
) -> None:
    validate_new_site_password(password)
    validate_password_confirm(password, password_confirm)
