"""Сборка read-моделей для админского экрана пользователей.

Один список «пользователь + суммарный трафик + число устройств» собирается без N+1: трафик и
устройства агрегируются отдельными запросами и подмешиваются к строкам в памяти.
"""

from __future__ import annotations

from typing import Literal, cast as type_cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.domain.list_sort import SortDir, order_clause
from app.core.time import utc_today
from app.domain.models.auth import SubscriptionConnectionItem
from app.domain.models.users import (
    ReferralBonusPolicy,
    StaffUsersListResponse,
    UserListItem,
)
from app.domain.referrals.referral_bonus_policy import normalize_referral_bonus_policy
from app.domain.referrals.repository import get_user_owned_referral_link
from app.domain.subscription.devices import list_subscription_connection_records_for_users
from app.domain.user_traffic import (
    user_server_traffic_latest_subquery,
    user_traffic_cumulative_for_user_at_calendar_boundary,
    user_traffic_total_by_user_as_of,
    user_traffic_total_by_user_strictly_before_calendar_day,
    user_traffic_totals,
)
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User


def _email_verified(user: User) -> bool:
    mail = (user.email or "").strip()
    return bool(mail) and user.email_verified_at is not None


def _normalize_account_role(raw: str | None) -> str:
    r = (raw or "client").strip()
    if r in ("client", "manager", "admin"):
        return r
    return "client"


async def _user_rows_count(
    session: AsyncSession,
    *,
    referral_link_id: int | None = None,
) -> int:
    stmt = select(func.count()).select_from(User)
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return int((await session.scalar(stmt)) or 0)


_STAFF_USER_SORT_KEYS = frozenset({
    "id",
    "email",
    "telegram",
    "role",
    "registered_at",
    "subscription_until",
    "subscription",
    "traffic",
    "devices",
    "referral_link_id",
})


def _user_list_order_by(
    sort_by: str | None,
    sort_dir: SortDir,
    *,
    traffic_agg,
    dev_agg,
):
    if sort_by is None or sort_by not in _STAFF_USER_SORT_KEYS:
        return (User.id.desc(),)
    columns = {
        "id": User.id,
        "email": User.email,
        "telegram": User.telegram_id,
        "role": User.account_role,
        "registered_at": User.registered_at,
        "subscription_until": User.subscription_until,
        "subscription": User.token,
        "traffic": func.coalesce(traffic_agg.c.total_bytes, 0),
        "devices": func.coalesce(dev_agg.c.dev_cnt, 0),
        "referral_link_id": User.referral_link_id,
    }
    primary = columns[sort_by]
    clauses = [order_clause(primary, sort_dir)]
    if sort_by != "id":
        clauses.append(User.id.desc())
    return tuple(clauses)


async def _user_rows_with_traffic(
    session: AsyncSession,
    *,
    referral_link_id: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
    sort_by: str | None = None,
    sort_dir: SortDir = "asc",
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
        .order_by(
            *_user_list_order_by(
                sort_by,
                sort_dir,
                traffic_agg=traffic_agg,
                dev_agg=dev_agg,
            ),
        )
    )
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
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
        email_verified=_email_verified(user),
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
        referral_bonus_policy=type_cast(
            ReferralBonusPolicy,
            normalize_referral_bonus_policy(user.referral_bonus_policy),
        ),
        token=(user.token if show_secrets else None),
        vless_uuid=(user.vless_uuid if show_secrets else None),
    )


async def _staff_user_list_items(
    session: AsyncSession,
    rows: list[tuple[User, int, int]],
    *,
    show_secrets: bool,
) -> list[UserListItem]:
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
                email_verified=_email_verified(user),
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
                referral_bonus_policy=type_cast(
                    ReferralBonusPolicy,
                    normalize_referral_bonus_policy(user.referral_bonus_policy),
                ),
                token=(user.token if show_secrets else None),
                vless_uuid=(user.vless_uuid if show_secrets else None),
            ),
        )
    return out


async def staff_list_users(
    session: AsyncSession,
    *,
    show_secrets: bool,
    referral_link_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str | None = None,
    sort_dir: SortDir = "asc",
) -> StaffUsersListResponse:
    """Пагинированный список пользователей для админ/менеджер интерфейса."""
    total = await _user_rows_count(session, referral_link_id=referral_link_id)
    rows = await _user_rows_with_traffic(
        session,
        referral_link_id=referral_link_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    items = await _staff_user_list_items(session, rows, show_secrets=show_secrets)
    return StaffUsersListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
