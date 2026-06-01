"""CRUD над ``referral_links`` и атомарные инкременты счётчиков.

Исключения этого модуля — типизированные подклассы :class:`app.core.exceptions.AppError`
(см. :mod:`app.domain.referrals.errors`): HTTP-код несёт сам тип ошибки, поэтому ни сервису,
ни эндпоинтам не нужно разбирать текст сообщения.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InternalServerError
from app.domain.referrals.errors import (
    PersonalReferralLinkExistsError,
    ReferralLinkNotFoundError,
    ReferralOwnerArgsError,
    ReferralTokenTakenError,
    ReferralUserNotFoundError,
)
from app.domain.referrals.tokens import (
    CounterKind,
    generate_referral_token,
    validate_token_shape,
)
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User


def _is_one_owner_per_user_conflict(e: IntegrityError) -> bool:
    """Срабатывание UNIQUE-индекса ``uq_referral_links_one_user_owner`` (PostgreSQL)."""
    diag = getattr(e.orig, "diag", None)
    cn = getattr(diag, "constraint_name", None) if diag is not None else None
    if cn == "uq_referral_links_one_user_owner":
        return True
    blob = f"{cn or ''}|{type(e.orig).__name__}|{str(e.orig)}"
    return "uq_referral_links_one_user_owner" in blob


async def get_user_owned_referral_link(
    session: AsyncSession, user_id: int,
) -> ReferralLink | None:
    """Личная ссылка пользователя (``owner_kind=user``); ``None`` — если ещё не создавалась."""
    return (
        await session.scalars(
            select(ReferralLink)
            .where(
                ReferralLink.owner_kind == "user",
                ReferralLink.owner_user_id == user_id,
            )
            .limit(1),
        )
    ).first()


async def create_user_owned_referral_link(
    session: AsyncSession,
    user_id: int,
    *,
    token: str | None,
) -> ReferralLink:
    """Создать персональную ссылку пользователя (не более одной — ``uq_*`` в миграции).

    Если ``token=None`` — генерируем случайный, иначе используем переданный (после ``strip``).
    """
    if await get_user_owned_referral_link(session, user_id) is not None:
        raise PersonalReferralLinkExistsError("У вас уже создана персональная реферальная ссылка")
    exists = await session.scalar(select(User.id).where(User.id == user_id).limit(1))
    if exists is None:
        raise ReferralUserNotFoundError

    raw = token.strip() if token else generate_referral_token()
    validate_token_shape(raw)
    row = ReferralLink(
        token=raw,
        owner_kind="user",
        owner_user_id=user_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        if _is_one_owner_per_user_conflict(e):
            raise PersonalReferralLinkExistsError(
                "У вас уже создана персональная реферальная ссылка",
            ) from e
        raise ReferralTokenTakenError from e
    return row


async def get_or_create_user_owned_referral_link(
    session: AsyncSession, user_id: int,
) -> ReferralLink:
    """Идемпотентный getter: если ссылка уже есть — вернёт её, иначе создаст.

    При коллизии случайного токена пробует ещё раз (до 16 попыток); если конкурент успел
    создать ссылку первым — вернёт уже существующую.
    """
    row = await get_user_owned_referral_link(session, user_id)
    if row is not None:
        return row
    for _ in range(16):
        try:
            return await create_user_owned_referral_link(session, user_id, token=None)
        except ReferralTokenTakenError:
            continue
        except PersonalReferralLinkExistsError:
            again = await get_user_owned_referral_link(session, user_id)
            if again is not None:
                return again
            raise
    raise InternalServerError("Не удалось сгенерировать уникальный реферальный токен")


async def create_referral_link(
    session: AsyncSession,
    *,
    owner_kind: str,
    owner_user_id: int | None,
    token: str | None = None,
) -> ReferralLink:
    """Создать любую реферальную запись (``user`` — личная, иначе именованный источник)."""
    kind = owner_kind.strip()
    if kind == "user":
        if owner_user_id is None:
            raise ReferralOwnerArgsError("Для owner_kind=user укажите owner_user_id")
        exists = await session.scalar(
            select(User.id).where(User.id == owner_user_id).limit(1),
        )
        if exists is None:
            raise ReferralUserNotFoundError("Пользователь с таким id не найден")
    else:
        if owner_user_id is not None:
            raise ReferralOwnerArgsError(
                "Для именованного источника (не user) поле owner_user_id должно быть пустым",
            )

    raw = token.strip() if token else generate_referral_token()
    validate_token_shape(raw)

    row = ReferralLink(
        token=raw,
        owner_kind=kind,
        owner_user_id=owner_user_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        if _is_one_owner_per_user_conflict(e):
            raise PersonalReferralLinkExistsError from e
        raise ReferralTokenTakenError from e
    return row


async def update_referral_link(
    session: AsyncSession,
    link_id: int,
    *,
    owner_kind: str,
    owner_user_id: int | None,
    token: str,
) -> ReferralLink:
    """Полное обновление записи; новый токен проверяется на занятость до записи."""
    row = await session.get(ReferralLink, link_id)
    if row is None:
        raise ReferralLinkNotFoundError

    kind = owner_kind.strip()
    if kind == "user":
        if owner_user_id is None:
            raise ReferralOwnerArgsError("Для owner_kind=user укажите owner_user_id")
        exists = await session.scalar(
            select(User.id).where(User.id == owner_user_id).limit(1),
        )
        if exists is None:
            raise ReferralUserNotFoundError("Пользователь с таким id не найден")
    else:
        if owner_user_id is not None:
            raise ReferralOwnerArgsError(
                "Для именованного источника (не user) поле owner_user_id должно быть пустым",
            )

    raw = token.strip()
    validate_token_shape(raw)

    if raw != row.token:
        taken = await session.scalar(
            select(ReferralLink.id)
            .where(ReferralLink.token == raw, ReferralLink.id != link_id)
            .limit(1),
        )
        if taken is not None:
            raise ReferralTokenTakenError

    row.token = raw
    row.owner_kind = kind
    row.owner_user_id = owner_user_id if kind == "user" else None
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        if _is_one_owner_per_user_conflict(e):
            raise PersonalReferralLinkExistsError from e
        raise ReferralTokenTakenError from e
    return row


async def delete_referral_link(session: AsyncSession, link_id: int) -> bool:
    """Удалить запись; ``True`` — если строка существовала."""
    row = await session.get(ReferralLink, link_id)
    if row is None:
        return False
    await session.delete(row)
    return True


async def increment_referral_counter(
    session: AsyncSession,
    link_id: int,
    kind: CounterKind,
) -> bool:
    """Атомарный ``+1`` к счётчику; ``True`` — если строка найдена."""
    stmt = update(ReferralLink).where(ReferralLink.id == link_id)
    if kind == "clicks":
        stmt = stmt.values(clicks_count=ReferralLink.clicks_count + 1)
    elif kind == "registrations":
        stmt = stmt.values(registrations_count=ReferralLink.registrations_count + 1)
    else:
        stmt = stmt.values(payments_count=ReferralLink.payments_count + 1)
    res = await session.execute(stmt)
    return res.rowcount > 0


async def increment_referral_counter_by_token(
    session: AsyncSession,
    token: str,
    kind: CounterKind,
) -> bool:
    """То же, что :func:`increment_referral_counter`, но по строковому токену из URL."""
    t = token.strip()
    if not t:
        return False
    row_id = await session.scalar(
        select(ReferralLink.id).where(ReferralLink.token == t).limit(1),
    )
    if row_id is None:
        return False
    return await increment_referral_counter(session, int(row_id), kind)
