"""Доверенные почтовые домены для регистрации и привязки нового email.

Список должен совпадать с ``frontend/src/auth/trustedEmailDomains.js``.
"""

from __future__ import annotations

from app.core.auth_env import normalize_email
from app.core.exceptions import BadRequestError

# Google
_GMAIL = frozenset({"gmail.com", "googlemail.com"})
# Yandex
_YANDEX = frozenset({
    "yandex.ru",
    "yandex.com",
    "yandex.by",
    "yandex.kz",
    "ya.ru",
})
# Mail.ru Group
_MAIL_RU = frozenset({"mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru", "xmail.ru"})
# Microsoft
_MICROSOFT = frozenset({"outlook.com", "hotmail.com", "live.com", "msn.com"})
# Apple
_APPLE = frozenset({"icloud.com", "me.com", "mac.com"})
# Proton
_PROTON = frozenset({"proton.me", "protonmail.com", "pm.me"})
# Rambler
_RAMBLER = frozenset({
    "rambler.ru",
    "lenta.ru",
    "ro.ru",
    "autorambler.ru",
    "myrambler.ru",
})
# Прочие крупные
_OTHER = frozenset({
    "gmx.com",
    "gmx.de",
    "gmx.net",
    "yahoo.com",
    "tuta.com",
    "tuta.io",
    "tutamail.com",
})

TRUSTED_EMAIL_DOMAINS: frozenset[str] = (
    _GMAIL
    | _YANDEX
    | _MAIL_RU
    | _MICROSOFT
    | _APPLE
    | _PROTON
    | _RAMBLER
    | _OTHER
)

UNTRUSTED_EMAIL_DOMAIN_MSG = (
    "Регистрация доступна только с почты доверенных сервисов"
)


def email_domain(email: str) -> str:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return ""
    return normalized.rsplit("@", 1)[-1]


def is_trusted_email_domain(email: str) -> bool:
    domain = email_domain(email)
    return bool(domain) and domain in TRUSTED_EMAIL_DOMAINS


def validate_trusted_email_domain(email: str) -> None:
    if is_trusted_email_domain(email):
        return
    raise BadRequestError(UNTRUSTED_EMAIL_DOMAIN_MSG)
