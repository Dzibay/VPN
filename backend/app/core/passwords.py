"""Хеширование паролей портала (bcrypt)."""

from __future__ import annotations

import logging

import bcrypt

log = logging.getLogger("app.passwords")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, password_hash: str | None) -> bool:
    """Сравнение пароля с bcrypt-хешем. Любая ошибка (битый хеш, UTF-8 в столбце,
    неправильный тип) трактуется как ``False`` — авторизация не удаётся, без traceback наружу."""

    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except (ValueError, TypeError):
        log.warning("verify_password: невалидный bcrypt-хеш в БД", exc_info=True)
        return False
