"""Создание реферальных токенов и атомарные инкременты счётчиков."""

from __future__ import annotations

import re
from urllib.parse import quote
import secrets
import string
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.subscription_public_base import site_address_to_public_origin
from app.models.referral_link import ReferralLink
from app.models.user import User

CounterKind = Literal["clicks", "registrations", "payments"]

# Telegram deep-link start: only A–Z, a–z, 0–9, _
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,64}$")

Alphabet = string.ascii_letters + string.digits + "_"


def generate_referral_token(length: int = 12) -> str:
    return "".join(secrets.choice(Alphabet) for _ in range(length))


def validate_token_shape(token: str) -> None:
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError(
            "token: допустимы латиница, цифры и подчёркивание, длина 4–64 (формат Telegram start)",
        )


def _referral_conflict_is_one_owner_per_user(e: IntegrityError) -> bool:
    """Срабатывание UNIQUE-индекса uq_referral_links_one_user_owner (PostgreSQL)."""
    diag = getattr(e.orig, "diag", None)
    cn = getattr(diag, "constraint_name", None) if diag is not None else None
    if cn == "uq_referral_links_one_user_owner":
        return True
    blob = f"{cn or ''}|{type(e.orig).__name__}|{str(e.orig)}"
    return "uq_referral_links_one_user_owner" in blob


def get_user_owned_referral_link(session: Session, user_id: int) -> ReferralLink | None:
    """Строка с owner_kind=user и данным пользователем (не более одной — см. ограничение в API/БД)."""
    return session.scalars(
        select(ReferralLink)
        .where(
            ReferralLink.owner_kind == "user",
            ReferralLink.owner_user_id == user_id,
        )
        .limit(1),
    ).first()


def create_user_owned_referral_link(
    session: Session,
    user_id: int,
    *,
    token: str | None,
) -> ReferralLink:
    """Личная ссылка: owner_kind=user, не более одной на аккаунт (см. миграцию uq_*)."""
    if get_user_owned_referral_link(session, user_id) is not None:
        raise ValueError("У вас уже создана персональная реферальная ссылка")
    exists = session.scalar(select(User.id).where(User.id == user_id).limit(1))
    if exists is None:
        raise ValueError("Пользователь не найден")

    raw = token.strip() if token else generate_referral_token()
    validate_token_shape(raw)
    row = ReferralLink(
        token=raw,
        owner_kind="user",
        owner_user_id=user_id,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        if _referral_conflict_is_one_owner_per_user(e):
            raise ValueError("У вас уже создана персональная реферальная ссылка") from e
        raise ValueError("Токен уже занят") from e
    return row


def create_referral_link(
    session: Session,
    *,
    owner_kind: str,
    owner_user_id: int | None,
    token: str | None = None,
) -> ReferralLink:
    kind = owner_kind.strip()
    if kind == "user":
        if owner_user_id is None:
            raise ValueError("Для owner_kind=user укажите owner_user_id")
        exists = session.scalar(select(User.id).where(User.id == owner_user_id).limit(1))
        if exists is None:
            raise ValueError("Пользователь с таким id не найден")
    else:
        if owner_user_id is not None:
            raise ValueError("Для именованного источника (не user) поле owner_user_id должно быть пустым")

    raw = token.strip() if token else generate_referral_token()
    validate_token_shape(raw)

    row = ReferralLink(
        token=raw,
        owner_kind=kind,
        owner_user_id=owner_user_id,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        if _referral_conflict_is_one_owner_per_user(e):
            raise ValueError(
                "У этого пользователя уже есть персональная реферальная ссылка (не более одной)",
            ) from e
        raise ValueError("Токен уже занят") from e
    return row


def update_referral_link(
    session: Session,
    link_id: int,
    *,
    owner_kind: str,
    owner_user_id: int | None,
    token: str,
) -> ReferralLink:
    row = session.get(ReferralLink, link_id)
    if row is None:
        raise ValueError("Запись не найдена")

    kind = owner_kind.strip()
    if kind == "user":
        if owner_user_id is None:
            raise ValueError("Для owner_kind=user укажите owner_user_id")
        exists = session.scalar(select(User.id).where(User.id == owner_user_id).limit(1))
        if exists is None:
            raise ValueError("Пользователь с таким id не найден")
    else:
        if owner_user_id is not None:
            raise ValueError("Для именованного источника (не user) поле owner_user_id должно быть пустым")

    raw = token.strip()
    validate_token_shape(raw)

    if raw != row.token:
        taken = session.scalar(
            select(ReferralLink.id).where(ReferralLink.token == raw, ReferralLink.id != link_id).limit(1)
        )
        if taken is not None:
            raise ValueError("Токен уже занят")

    row.token = raw
    row.owner_kind = kind
    row.owner_user_id = owner_user_id if kind == "user" else None
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        if _referral_conflict_is_one_owner_per_user(e):
            raise ValueError(
                "У этого пользователя уже есть персональная реферальная ссылка (не более одной)",
            ) from e
        raise ValueError("Токен уже занят") from e
    return row


def increment_referral_counter(
    session: Session,
    link_id: int,
    kind: CounterKind,
) -> bool:
    """Увеличить счётчик на 1; возвращает True если строка найдена."""
    stmt = update(ReferralLink).where(ReferralLink.id == link_id)
    if kind == "clicks":
        stmt = stmt.values(clicks_count=ReferralLink.clicks_count + 1)
    elif kind == "registrations":
        stmt = stmt.values(registrations_count=ReferralLink.registrations_count + 1)
    else:
        stmt = stmt.values(payments_count=ReferralLink.payments_count + 1)
    res = session.execute(stmt)
    return res.rowcount > 0


def increment_referral_counter_by_token(
    session: Session,
    token: str,
    kind: CounterKind,
) -> bool:
    """По строковому token (после strip)."""
    t = token.strip()
    if not t:
        return False
    row_id = session.scalar(select(ReferralLink.id).where(ReferralLink.token == t).limit(1))
    if row_id is None:
        return False
    return increment_referral_counter(session, int(row_id), kind)


def referral_site_register_url(settings: object, token: str) -> str | None:
    """Публичная ссылка на главную SPA с ?ref= ."""
    base = public_spa_base_url(settings)
    if not base:
        return None
    return f"{base}/?ref={quote(token, safe='')}"


def _telegram_bot_username_clean(settings: object) -> str:
    return (getattr(settings, "telegram_bot_username", None) or "").strip().lstrip("@")


def referral_telegram_deep_link(settings: object, token: str) -> str | None:
    """https://t.me/{TELEGRAM_BOT_USERNAME}?start=token"""
    bot = _telegram_bot_username_clean(settings)
    if not bot:
        return None
    return f"https://t.me/{bot}?start={quote(token, safe='')}"


def telegram_bot_public_page_url(settings: object) -> str | None:
    """https://t.me/{username} без deep-link (ЛК, привязка аккаунта)."""
    bot = _telegram_bot_username_clean(settings)
    if not bot:
        return None
    return f"https://t.me/{bot}"


def public_spa_base_url(settings: object) -> str | None:
    """Публичный origin SPA из SITE_ADRESS (settings.site_address), без других источников."""

    from_site = site_address_to_public_origin(getattr(settings, "site_address", None) or "")
    return from_site or None


def referral_link_to_out(link: ReferralLink, settings: object):
    """Сборка ответа админ-API с подставленными URL из конфига."""
    from app.schemas.referral_links import ReferralLinkOut, ReferralLinkRead

    core = ReferralLinkRead.model_validate(link)
    return ReferralLinkOut(
        **core.model_dump(),
        site_entry_url=referral_site_register_url(settings, link.token),
        telegram_deep_link=referral_telegram_deep_link(settings, link.token),
    )
