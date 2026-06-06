"""Пользователи: сводка по регистрациям и админский CRUD.

Чтобы модуль остался читаемым, объёмные части вынесены в пакет :mod:`app.domain.users` и
реэкспортируются ниже (внешний код импортирует их отсюда без изменений):

* сборка списка для админки — :mod:`app.domain.users.staff_listing`,
* поиск пользователей — :mod:`app.domain.users.search`,
* идентификаторы/токены — :mod:`app.domain.users.identifiers`,
* системные дневные метрики и per-user analytics — :mod:`app.domain.users.{daily_stats,traffic_breakdown}`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.time import ensure_utc, moscow_day_bounds_utc, moscow_today
from app.domain.models.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    UserCreate,
    UsersCountResponse,
    UserUpdate,
)
from app.domain.subscription.traffic_limit import apply_default_traffic_limit_for_new_client
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.users.search import search_staff_users
from app.domain.users.staff_listing import (
    staff_get_user_list_item,
    staff_list_users,
)
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.users_service")

__all__ = [
    "users_count",
    "create_staff_user",
    "extend_active_subscriptions",
    "delete_staff_user",
    "patch_staff_user",
    "require_user_exists",
    # Реэкспорт доменных подмодулей (обратная совместимость импортов).
    "staff_get_user_list_item",
    "staff_list_users",
    "search_staff_users",
]


def _mean_registration_gap_ms(times: list[datetime]) -> float | None:
    if len(times) < 2:
        return None
    sum_ms = 0.0
    n = 0
    for i in range(1, len(times)):
        gap = (times[i] - times[i - 1]).total_seconds() * 1000.0
        if gap >= 0:
            sum_ms += gap
            n += 1
    return (sum_ms / n) if n > 0 else None


async def users_count(session: AsyncSession) -> UsersCountResponse:
    """Общее число записей в ``users`` и сводка по регистрациям для виджетов админки."""
    total = int((await session.scalar(select(func.count()).select_from(User))) or 0)
    today = moscow_today()
    yesterday = today - timedelta(days=1)
    start_today, end_today = moscow_day_bounds_utc(today)
    start_yesterday, _ = moscow_day_bounds_utc(yesterday)

    regs_today = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.registered_at.is_not(None),
                    User.registered_at >= start_today,
                    User.registered_at < end_today,
                ),
            )
        )
        or 0,
    )
    regs_yesterday = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.registered_at.is_not(None),
                    User.registered_at >= start_yesterday,
                    User.registered_at < start_today,
                ),
            )
        )
        or 0,
    )

    all_times = [
        t
        for t in (
            await session.scalars(
                select(User.registered_at).where(
                    User.registered_at.is_not(None),
                    User.subscription_until.is_not(None),
                ),
            )
        ).all()
        if t is not None
    ]
    all_times.sort()
    today_times = sorted(
        ut
        for t in all_times
        if start_today <= (ut := ensure_utc(t)) < end_today
    )

    return UsersCountResponse(
        users_count=total,
        registrations_today_count=regs_today,
        registrations_yesterday_count=regs_yesterday,
        registration_gap_overall_ms=_mean_registration_gap_ms(all_times),
        registration_gap_today_ms=_mean_registration_gap_ms(today_times),
    )


async def create_staff_user(session: AsyncSession, body: UserCreate) -> User:
    """Создать пользователя из админки; токен подписки и VLESS UUID генерируются здесь."""
    user = User(
        telegram_id=body.telegram_id,
        telegram_properties=body.telegram_properties,
        subscription_until=body.subscription_until,
        account_role="client",
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    apply_default_traffic_limit_for_new_client(user)
    try:
        await table_insert(session, user)
    except IntegrityError as e:
        log.warning("create_user conflict: %s", e)
        raise ConflictError(
            "Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    return user


async def extend_active_subscriptions(
    session: AsyncSession,
    body: ExtendActiveSubscriptionsBody,
) -> ExtendActiveSubscriptionsResponse:
    """Продлить подписку всем пользователям с активной конечной датой на ``body.days`` дней.

    Пользователи без срока (``subscription_until IS NULL``) не затрагиваются.
    """
    days = body.days
    stmt = (
        update(User)
        .where(
            User.subscription_until.isnot(None),
            User.subscription_until >= moscow_today(),
        )
        .values(subscription_until=User.subscription_until + days)
    )
    result = await session.execute(stmt)
    n = int(result.rowcount or 0)
    return ExtendActiveSubscriptionsResponse(updated_count=n)


async def delete_staff_user(session: AsyncSession, user_id: int) -> None:
    """Удалить пользователя; вызывающий код ставит синхронизацию Xray в ``BackgroundTasks``."""
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    await session.delete(user)


async def patch_staff_user(session: AsyncSession, user_id: int, body: UserUpdate) -> User:
    """Частичное обновление пользователя из админки.

    При попытке выставить ``account_role='admin'`` без ``password_hash`` отдаёт 400: вход
    в админку требует пароль на сайте.
    """
    from app.constants import REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT
    from app.domain.referrals.referral_bonus_policy import normalize_referral_bonus_policy
    from app.domain.referrals.task_bonus_days import (
        apply_pending_referral_bonus_days_to_subscription,
    )

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return user
    new_role = data.get("account_role")
    if new_role == "admin" and not user.password_hash:
        raise BadRequestError(
            "Нельзя назначить роль admin без пароля у пользователя",
        )
    policy_transition_to_instant = False
    if "referral_bonus_policy" in data:
        new_policy = normalize_referral_bonus_policy(data["referral_bonus_policy"])
        old_policy = normalize_referral_bonus_policy(user.referral_bonus_policy)
        policy_transition_to_instant = (
            new_policy == REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT
            and old_policy != REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT
        )
        data["referral_bonus_policy"] = new_policy
    for key, value in data.items():
        setattr(user, key, value)
    if policy_transition_to_instant:
        await apply_pending_referral_bonus_days_to_subscription(session, user)
    await session.flush()
    return user


async def require_user_exists(session: AsyncSession, user_id: int) -> User:
    """Проверка существования пользователя для эндпоинтов аналитики (404 на отсутствие)."""
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user
