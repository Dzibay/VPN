"""Админские CRUD-операции с пользователями и общий список с агрегатами трафика и устройств.

Низкоуровневые примитивы вынесены в пакет :mod:`app.domain.users`:

* идентификаторы — :mod:`app.domain.users.identifiers`,
* очередь синхронизации Xray — :mod:`app.domain.users.xray_sync_queue`,
* системные дневные метрики — :mod:`app.domain.users.daily_stats`,
* per-user analytics — :mod:`app.domain.users.traffic_breakdown`.
"""

from __future__ import annotations

import logging
from typing import Literal, cast as type_cast

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.time import utc_today
from app.domain.models.auth import SubscriptionConnectionItem
from app.domain.models.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    StaffUserSearchItem,
    UserCreate,
    UserListItem,
    UsersCountResponse,
    UserUpdate,
)
from app.domain.referrals.repository import get_user_owned_referral_link
from app.domain.subscription.devices import list_subscription_connection_records_for_users
from app.domain.subscription.traffic_limit import apply_default_traffic_limit_for_new_client
from app.domain.user_traffic import (
    user_server_traffic_latest_subquery,
    user_traffic_cumulative_for_user_at_calendar_boundary,
    user_traffic_total_by_user_as_of,
    user_traffic_total_by_user_strictly_before_calendar_day,
    user_traffic_totals,
)
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.users_service")


def _normalize_account_role(raw: str | None) -> str:
    r = (raw or "client").strip()
    if r in ("client", "manager", "admin"):
        return r
    return "client"


async def _user_rows_with_traffic(
    session: AsyncSession,
    *,
    referral_link_id: int | None = None,
) -> list[tuple[User, int, int]]:
    """Список ``(user, total_bytes, devices_count)`` для админского экрана пользователей.

    Один запрос с outer-join'ами, чтобы не делать N+1 на каждого пользователя при подсчёте
    суммарного трафика и числа подписочных устройств.

    При ``referral_link_id`` — только пользователи с таким ``users.referral_link_id``
    (атрибуция при регистрации).
    """
    latest = user_server_traffic_latest_subquery()
    traffic_agg = (
        select(
            latest.c.user_id.label("uid"),
            func.coalesce(
                func.sum(latest.c.up_bytes + latest.c.down_bytes),
                0,
            ).label("total_bytes"),
        )
        .group_by(latest.c.user_id)
        .subquery()
    )
    dev_agg = (
        select(
            SubscriptionDevice.user_id.label("uid"),
            func.count(SubscriptionDevice.id).label("dev_cnt"),
        )
        .group_by(SubscriptionDevice.user_id)
        .subquery()
    )
    stmt = (
        select(
            User,
            func.coalesce(traffic_agg.c.total_bytes, 0).label("total_traffic"),
            func.coalesce(dev_agg.c.dev_cnt, 0).label("device_count"),
        )
        .outerjoin(traffic_agg, User.id == traffic_agg.c.uid)
        .outerjoin(dev_agg, User.id == dev_agg.c.uid)
        .order_by(User.id.desc())
    )
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return list((await session.execute(stmt)).all())


async def _user_ids_with_any_payment(
    session: AsyncSession,
    user_ids: list[int],
) -> set[int]:
    """Пользователи с хотя бы одной строкой в ``payments``."""
    if not user_ids:
        return set()
    stmt = select(Payment.user_id).where(Payment.user_id.in_(user_ids)).distinct()
    return {int(uid) for uid in (await session.scalars(stmt)).all()}


async def users_count(session: AsyncSession) -> UsersCountResponse:
    """Общее число записей в ``users``."""
    total = await session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


async def staff_get_user_list_item(
    session: AsyncSession,
    user_id: int,
    *,
    show_secrets: bool,
) -> UserListItem:
    """Одна строка пользователя в формате списка админки (агрегаты и устройства)."""
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    _, _, total_raw = await user_traffic_totals(session, user_id)
    total = int(total_raw or 0)
    if total < 0:
        total = 0
    dev_stmt = select(func.coalesce(func.count(SubscriptionDevice.id), 0)).where(
        SubscriptionDevice.user_id == user_id,
    )
    dev_n = int((await session.scalar(dev_stmt)) or 0)
    if dev_n < 0:
        dev_n = 0
    devices_map = await list_subscription_connection_records_for_users(session, [user_id])
    raw_devs = devices_map.get(int(user.id), [])
    subs_devices = [SubscriptionConnectionItem(**r) for r in raw_devs]
    today_utc = utc_today()
    t_prev = await user_traffic_cumulative_for_user_at_calendar_boundary(
        session,
        user_id,
        today_utc,
        inclusive=False,
    )
    t_now = await user_traffic_cumulative_for_user_at_calendar_boundary(
        session,
        user_id,
        today_utc,
        inclusive=True,
    )
    active_today = t_now > t_prev
    paid_ids = await _user_ids_with_any_payment(session, [user_id])
    has_payments = user_id in paid_ids
    role = _normalize_account_role(user.account_role)
    role_lit = type_cast(Literal["client", "manager", "admin"], role)
    owned_row = await get_user_owned_referral_link(session, user_id)
    owned_referral_link_id = int(owned_row.id) if owned_row is not None else None
    return UserListItem(
        id=user.id,
        registered_at=user.registered_at,
        email=user.email,
        account_role=role_lit,
        telegram_id=user.telegram_id,
        telegram_properties=user.telegram_properties,
        subscription_until=user.subscription_until,
        total_traffic_bytes=total,
        active_today=active_today,
        has_payments=has_payments,
        traffic_limit_bytes=(
            int(user.traffic_limit_bytes) if user.traffic_limit_bytes is not None else None
        ),
        subscription_devices_count=dev_n,
        subscription_devices=subs_devices,
        referral_link_id=user.referral_link_id,
        owned_referral_link_id=owned_referral_link_id,
        token=(user.token if show_secrets else None),
        vless_uuid=(user.vless_uuid if show_secrets else None),
    )


async def staff_list_users(
    session: AsyncSession,
    *,
    show_secrets: bool,
    referral_link_id: int | None = None,
) -> list[UserListItem]:
    """Список пользователей для админ/менеджер интерфейса.

    ``show_secrets`` — раскрывать ли токен подписки и UUID VLESS (только для админа: для менеджера
    эти поля приходят как ``None``).

    ``referral_link_id`` — если задан, только пользователи, у которых при регистрации
    зафиксирована эта реферальная ссылка.
    """
    rows = await _user_rows_with_traffic(session, referral_link_id=referral_link_id)
    user_ids = [int(user.id) for user, _, _ in rows]
    devices_map = await list_subscription_connection_records_for_users(session, user_ids)
    today_utc = utc_today()
    totals_last_before_today = await user_traffic_total_by_user_strictly_before_calendar_day(
        session,
        today_utc,
    )
    totals_through_today = await user_traffic_total_by_user_as_of(session, today_utc)
    paid_user_ids = await _user_ids_with_any_payment(session, user_ids)
    out: list[UserListItem] = []
    for user, total_raw, dev_raw in rows:
        try:
            total = int(total_raw or 0)
        except (TypeError, ValueError):
            total = 0
        if total < 0:
            total = 0
        try:
            dev_n = int(dev_raw or 0)
        except (TypeError, ValueError):
            dev_n = 0
        if dev_n < 0:
            dev_n = 0
        role = _normalize_account_role(user.account_role)
        role_lit = type_cast(Literal["client", "manager", "admin"], role)
        raw_devs = devices_map.get(int(user.id), [])
        subs_devices = [SubscriptionConnectionItem(**r) for r in raw_devs]
        uid = int(user.id)
        t_prev = int(totals_last_before_today.get(uid, 0))
        t_now = int(totals_through_today.get(uid, 0))
        active_today = t_now > t_prev
        has_payments = uid in paid_user_ids
        out.append(
            UserListItem(
                id=user.id,
                registered_at=user.registered_at,
                email=user.email,
                account_role=role_lit,
                telegram_id=user.telegram_id,
                telegram_properties=user.telegram_properties,
                subscription_until=user.subscription_until,
                total_traffic_bytes=total,
                active_today=active_today,
                has_payments=has_payments,
                traffic_limit_bytes=(
                    int(user.traffic_limit_bytes)
                    if user.traffic_limit_bytes is not None
                    else None
                ),
                subscription_devices_count=dev_n,
                subscription_devices=subs_devices,
                referral_link_id=user.referral_link_id,
                owned_referral_link_id=None,
                token=(user.token if show_secrets else None),
                vless_uuid=(user.vless_uuid if show_secrets else None),
            ),
        )
    return out


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
            User.subscription_until >= utc_today(),
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
    for key, value in data.items():
        setattr(user, key, value)
    await session.flush()
    return user


async def require_user_exists(session: AsyncSession, user_id: int) -> User:
    """Проверка существования пользователя для эндпоинтов аналитики (404 на отсутствие)."""
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user


def _escape_like_pattern(fragment: str) -> str:
    return (
        fragment.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


async def search_staff_users(
    session: AsyncSession,
    *,
    q: str,
    limit: int = 30,
) -> list[StaffUserSearchItem]:
    """Поиск по email, telegram_id (подстрока в тексте), telegram_properties.username (ILIKE)."""
    raw = q.strip()
    if len(raw) < 3:
        return []
    cap = min(max(1, limit), 50)
    pattern = f"%{_escape_like_pattern(raw)}%"
    username_ast = User.telegram_properties["username"].astext
    stmt = (
        select(User)
        .where(
            or_(
                User.email.ilike(pattern, escape="\\"),
                cast(User.telegram_id, String).ilike(pattern, escape="\\"),
                func.coalesce(username_ast, "").ilike(pattern, escape="\\"),
            ),
        )
        .order_by(User.id.desc())
        .limit(cap)
    )
    rows = list((await session.scalars(stmt)).all())
    out: list[StaffUserSearchItem] = []
    for u in rows:
        props = u.telegram_properties if isinstance(u.telegram_properties, dict) else None
        uname = props.get("username") if props else None
        if isinstance(uname, str):
            uname = uname.strip() or None
        else:
            uname = None
        out.append(
            StaffUserSearchItem(
                id=int(u.id),
                email=u.email,
                telegram_id=int(u.telegram_id) if u.telegram_id is not None else None,
                telegram_username=uname,
            ),
        )
    return out
