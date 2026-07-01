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

from sqlalchemy import func, select, text, update
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
from app.domain.auth.email_verify_tokens import (
    EmailVerifyRedisError,
    purge_email_verify_for_user,
)
from app.domain.auth.sync_tokens import (
    TelegramSyncRedisError,
    purge_telegram_link_tokens_for_user,
)
from app.domain.subscription.traffic_limit import apply_default_traffic_limit_for_new_client
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.users.stats_qualification import (
    user_counts_in_admin_stats,
    user_unverified_email_without_telegram,
)
from app.domain.tenant.admin_project_scope import (
    admin_project_id,
    merge_project_sql_params,
    project_scope_clause,
    user_table_project_filter_sql,
)
from app.infrastructure.cache import get_redis
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
    "delete_staff_users_bulk",
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
    """Сводка для виджетов админки: только учётные пользователи (Telegram или email ✓)."""
    stats_user = user_counts_in_admin_stats(User)
    unverified = user_unverified_email_without_telegram(User)
    scope = project_scope_clause(User)
    pid = admin_project_id()

    def _scoped(*parts):
        if scope is not None:
            return (scope, *parts)
        return parts

    today = moscow_today()
    yesterday = today - timedelta(days=1)
    start_today, end_today = moscow_day_bounds_utc(today)
    start_yesterday, _ = moscow_day_bounds_utc(yesterday)

    total = int(
        (await session.scalar(
            select(func.count()).select_from(User).where(*_scoped(stats_user)),
        )) or 0,
    )
    unverified_total = int(
        (await session.scalar(
            select(func.count()).select_from(User).where(*_scoped(unverified)),
        )) or 0,
    )

    regs_today = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    *_scoped(
                        stats_user,
                        User.registered_at.is_not(None),
                        User.registered_at >= start_today,
                        User.registered_at < end_today,
                    ),
                ),
            )
        )
        or 0,
    )
    regs_today_unverified = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    *_scoped(
                        unverified,
                        User.registered_at.is_not(None),
                        User.registered_at >= start_today,
                        User.registered_at < end_today,
                    ),
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
                    *_scoped(
                        stats_user,
                        User.registered_at.is_not(None),
                        User.registered_at >= start_yesterday,
                        User.registered_at < start_today,
                    ),
                ),
            )
        )
        or 0,
    )

    project_sql = user_table_project_filter_sql("u", project_id=pid)
    gap_overall_stmt = text(
        f"""
        WITH ordered AS (
            SELECT u.registered_at
            FROM users u
            WHERE u.registered_at IS NOT NULL
              AND u.subscription_until IS NOT NULL
              {project_sql}
              AND (
                  u.telegram_id IS NOT NULL
                  OR (
                      u.email IS NOT NULL
                      AND BTRIM(u.email) <> ''
                      AND u.email_verified_at IS NOT NULL
                  )
              )
        ),
        gaps AS (
            SELECT EXTRACT(EPOCH FROM (
                registered_at - LAG(registered_at) OVER (ORDER BY registered_at)
            )) * 1000 AS gap_ms
            FROM ordered
        )
        SELECT AVG(gap_ms) FROM gaps WHERE gap_ms IS NOT NULL
        """,
    )
    gap_today_stmt = text(
        f"""
        WITH ordered AS (
            SELECT u.registered_at
            FROM users u
            WHERE u.registered_at IS NOT NULL
              AND u.subscription_until IS NOT NULL
              AND u.registered_at >= :start_today
              AND u.registered_at < :end_today
              {project_sql}
              AND (
                  u.telegram_id IS NOT NULL
                  OR (
                      u.email IS NOT NULL
                      AND BTRIM(u.email) <> ''
                      AND u.email_verified_at IS NOT NULL
                  )
              )
        ),
        gaps AS (
            SELECT EXTRACT(EPOCH FROM (
                registered_at - LAG(registered_at) OVER (ORDER BY registered_at)
            )) * 1000 AS gap_ms
            FROM ordered
        )
        SELECT AVG(gap_ms) FROM gaps WHERE gap_ms IS NOT NULL
        """,
    )
    gap_overall_raw = await session.scalar(
        gap_overall_stmt,
        merge_project_sql_params(project_id=pid),
    )
    gap_today_raw = await session.scalar(
        gap_today_stmt,
        merge_project_sql_params(
            {"start_today": start_today, "end_today": end_today},
            project_id=pid,
        ),
    )
    gap_overall = float(gap_overall_raw) if gap_overall_raw is not None else None
    gap_today = float(gap_today_raw) if gap_today_raw is not None else None

    return UsersCountResponse(
        users_count=total,
        unverified_email_users_count=unverified_total,
        registrations_today_count=regs_today,
        registrations_today_unverified_email_count=regs_today_unverified,
        registrations_yesterday_count=regs_yesterday,
        registration_gap_overall_ms=gap_overall,
        registration_gap_today_ms=gap_today,
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


def _purge_user_redis_keys(user_id: int) -> None:
    """Best-effort: одноразовые токены email/Telegram в Redis после удаления users.id."""
    try:
        redis = get_redis()
        purge_email_verify_for_user(redis, user_id)
        purge_telegram_link_tokens_for_user(redis, user_id)
    except (EmailVerifyRedisError, TelegramSyncRedisError):
        log.warning(
            "delete_staff_user: Redis недоступен, ключи user_id=%s не очищены",
            user_id,
            exc_info=True,
        )


async def delete_staff_user(session: AsyncSession, user_id: int) -> None:
    """Удалить пользователя и связанные строки (FK ON DELETE CASCADE/SET NULL в БД).

    Каскадно удаляются: ``user_server_traffic``, ``subscription_devices``,
    ``support_messages`` (как клиент), ``payments``, ``tasks`` (где ``user_id``),
    ``referral_links`` (где ``owner_user_id``). Обнуляются: ``users.referral_link_id``
    у приглашённых, ``user_http_request_traces.user_id``, ``tasks.referee_id``,
    ``support_messages.staff_user_id``, ``created_by``/``updated_by`` в бухгалтерии.

    Вызывающий код ставит синхронизацию Xray в ``BackgroundTasks``.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    _purge_user_redis_keys(user_id)
    await session.delete(user)


async def delete_staff_users_bulk(session: AsyncSession, *, ids: list[int]) -> int:
    """Удалить нескольких пользователей; несуществующие id пропускаются."""
    uniq_ids = sorted({int(v) for v in ids if int(v) > 0})
    if not uniq_ids:
        return 0
    deleted = 0
    for user_id in uniq_ids:
        user = await session.get(User, user_id)
        if user is None:
            continue
        _purge_user_redis_keys(user_id)
        await session.delete(user)
        deleted += 1
    return deleted


async def patch_staff_user(session: AsyncSession, user_id: int, body: UserUpdate) -> User:
    """Частичное обновление пользователя из админки.

    При попытке выставить ``account_role='admin'`` без ``password_hash`` отдаёт 400: вход
    в админку требует пароль на сайте.
    """
    from app.constants import REFERRAL_BONUS_POLICY_FIXED_FIRST_PAYMENT_INSTANT
    from app.domain.balance.money import rub_to_kopecks
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
    if new_role in ("admin", "manager"):
        raise BadRequestError(
            "Роли admin и manager задаются только в staff_users (админ-панель на отдельном домене)",
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
    if "referral_fixed_bonus_rub" in data:
        rub = data.pop("referral_fixed_bonus_rub")
        if rub is None:
            user.referral_fixed_bonus_kopecks = None
        else:
            user.referral_fixed_bonus_kopecks = rub_to_kopecks(int(rub))
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
