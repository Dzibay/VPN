"""Создание реферальных токенов и атомарные инкременты счётчиков."""

from __future__ import annotations

import re
from urllib.parse import quote
import secrets
import string
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.subscription_public_base import site_address_to_public_origin
from app.domain.services.http_errors import HttpServiceError
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User

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


def get_or_create_user_owned_referral_link(session: Session, user_id: int) -> ReferralLink:
    """Вернуть личную ссылку пользователя или создать одну (идемпотентно, с повтором при коллизии токена)."""
    row = get_user_owned_referral_link(session, user_id)
    if row is not None:
        return row
    for _ in range(16):
        try:
            return create_user_owned_referral_link(session, user_id, token=None)
        except ValueError as e:
            msg = str(e)
            if msg == "Пользователь не найден":
                raise
            if msg == "Токен уже занят":
                continue
            again = get_user_owned_referral_link(session, user_id)
            if again is not None:
                return again
            raise
    raise RuntimeError("Не удалось сгенерировать уникальный реферальный токен")


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
    from app.domain.models.referral_links import ReferralLinkOut, ReferralLinkRead

    core = ReferralLinkRead.model_validate(link)
    return ReferralLinkOut(
        **core.model_dump(),
        site_entry_url=referral_site_register_url(settings, link.token),
        telegram_deep_link=referral_telegram_deep_link(settings, link.token),
    )


def _nz_metric(v: object) -> int:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, n)


def list_staff_referral_links(session: Session, cfg: object) -> list:
    stmt = select(ReferralLink).order_by(ReferralLink.id.desc())
    rows = list(session.scalars(stmt).all())
    return [referral_link_to_out(r, cfg) for r in rows]


def referral_funnel_compute(session: Session, referral_link_id: int | None, _cfg: object):
    from app.domain.models.referral_links import ReferralFunnelSummary

    latest = user_server_traffic_latest_subquery()
    per_user_traffic = (
        select(
            latest.c.user_id.label("uid"),
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            ).label("tot"),
        )
        .group_by(latest.c.user_id)
        .having(
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            )
            > 0,
        )
        .subquery()
    )

    if referral_link_id is not None:
        row = session.scalars(
            select(ReferralLink).where(ReferralLink.id == referral_link_id).limit(1),
        ).first()
        if row is None:
            raise HttpServiceError(404, "Реферальная ссылка не найдена")
        registrations_total_raw = row.registrations_count
        users_with_traffic_raw = session.scalar(
            select(func.count())
            .select_from(per_user_traffic)
            .join(User, User.id == per_user_traffic.c.uid)
            .where(User.referral_link_id == referral_link_id),
        )
        return ReferralFunnelSummary(
            clicks_total=_nz_metric(row.clicks_count),
            registrations_total=_nz_metric(registrations_total_raw),
            users_with_traffic=_nz_metric(users_with_traffic_raw),
        )

    registrations_total_raw = session.scalar(select(func.count()).select_from(User))
    users_with_traffic_raw = session.scalar(select(func.count()).select_from(per_user_traffic))

    return ReferralFunnelSummary(
        clicks_total=None,
        registrations_total=_nz_metric(registrations_total_raw),
        users_with_traffic=_nz_metric(users_with_traffic_raw),
    )


def delete_referral_link_row(session: Session, link_id: int) -> None:
    stmt = select(ReferralLink).where(ReferralLink.id == link_id).limit(1)
    row = session.scalars(stmt).first()
    if row is None:
        raise HttpServiceError(404, "Токен не найден")
    session.delete(row)


def client_site_user_id(principal: object) -> int:
    role = getattr(principal, "role", None)
    uid = getattr(principal, "user_id", None)
    if role != "user":
        raise HttpServiceError(
            403,
            "Персональная реферальная ссылка доступна только для учётной записи "
            "клиента (токены для сотрудников — через админ-панель).",
        )
    if uid is None:
        raise HttpServiceError(401, "Недействительный токен")
    return int(uid)


def referral_me_for_user(session: Session, user_id: int, cfg: object):
    from app.domain.models.referral_links import ReferralMeResponse

    try:
        row = get_or_create_user_owned_referral_link(session, user_id)
    except ValueError as e:
        msg = str(e)
        if msg == "Пользователь не найден":
            raise HttpServiceError(404, msg) from e
        raise HttpServiceError(422, msg) from e
    except RuntimeError as e:
        raise HttpServiceError(500, str(e)) from e

    return ReferralMeResponse(link=referral_link_to_out(row, cfg))
