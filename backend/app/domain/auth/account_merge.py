"""Объединение двух учётных записей пользователя в одну.

Используется при привязке Telegram к существующему сайтовому аккаунту: если в БД уже есть
запись с тем же ``telegram_id``, нужно перенести трафик (по узлам и дням **суммируется**
с трафиком основного аккаунта), реферальную ссылку и прочие данные на основной аккаунт
и удалить дубликат, не теряя пользовательских данных.

Перед удалением дубликата строки ``payments``, ``tasks`` (поля ``user_id`` и ``referee_id``),
``subscription_devices`` и ``user_http_request_traces`` с ``user_id`` дубликата перепривязываются
на основной ``users.id`` (иначе CASCADE удалял бы оплаты и задачи бота).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.referrals.repository import get_user_owned_referral_link
from app.infrastructure.persistence.models.payment import Payment
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.task import Task
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_http_request_trace import UserHttpRequestTrace
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


def _later_subscription_date(a: date | None, b: date | None) -> date | None:
    """Самая поздняя из двух дат окончания подписки.

    После слияния учёток у итогового пользователя должно остаться больше календарных дней
    доступа из двух (пример: +10 дней vs +14 дней → остаётся +14).
    """
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


async def merge_user_server_traffic(
    session: AsyncSession,
    keep_user_id: int,
    drop_user_id: int,
) -> None:
    """Перенести ``user_server_traffic`` с ``drop_user_id`` на ``keep_user_id``.

    Для каждой пары (``server_id``, ``traffic_date``) у обоих аккаунтов байты **складываются**
    в одну строку на ``keep_user_id`` (и ``raw_*`` тоже), затем строка ``drop`` удаляется.
    Составной ключ как в ``xray_stats_collect``: ``(user_id, server_id, traffic_date)``.
    """
    rows = (
        await session.scalars(
            select(UserServerTraffic).where(UserServerTraffic.user_id == drop_user_id),
        )
    ).all()
    for row in rows:
        pk = (keep_user_id, row.server_id, row.traffic_date)
        exist = await session.get(UserServerTraffic, pk)
        if exist is None:
            session.add(
                UserServerTraffic(
                    user_id=keep_user_id,
                    server_id=row.server_id,
                    traffic_date=row.traffic_date,
                    up_bytes=row.up_bytes,
                    down_bytes=row.down_bytes,
                    raw_up=row.raw_up,
                    raw_down=row.raw_down,
                ),
            )
        else:
            exist.up_bytes += row.up_bytes
            exist.down_bytes += row.down_bytes
            exist.raw_up += row.raw_up
            exist.raw_down += row.raw_down
        await session.delete(row)
    await session.flush()


async def merge_owned_referral_links(
    session: AsyncSession,
    keep_user_id: int,
    drop_user_id: int,
) -> None:
    """Перенести личную реферальную ссылку с ``drop`` на ``keep``.

    Если у обоих были собственные ссылки — складывает счётчики на ссылку ``keep``
    и удаляет ссылку ``drop``; если ссылка только у ``drop`` — переподвешивает её.
    """
    la = await get_user_owned_referral_link(session, keep_user_id)
    lb = await get_user_owned_referral_link(session, drop_user_id)
    if lb is None:
        return
    if la is None:
        lb.owner_user_id = keep_user_id
        await session.flush()
        return
    la.clicks_count += lb.clicks_count
    la.registrations_count += lb.registrations_count
    la.payments_count += lb.payments_count
    await session.delete(lb)
    await session.flush()


def _dt_cmp(a: datetime | None, b: datetime | None) -> int:
    """Сравнение моментов времени для выбора более «свежей» строки устройства (-1 / 0 / 1)."""
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    try:
        if a < b:
            return -1
        if a > b:
            return 1
    except TypeError:
        ta = a.timestamp()
        tb = b.timestamp()
        if ta < tb:
            return -1
        if ta > tb:
            return 1
    return 0


async def merge_reassign_payments(session: AsyncSession, *, keep_user_id: int, drop_user_id: int) -> None:
    await session.execute(
        update(Payment).where(Payment.user_id == drop_user_id).values(user_id=keep_user_id),
    )


async def merge_reassign_tasks(session: AsyncSession, *, keep_user_id: int, drop_user_id: int) -> None:
    """Все ``tasks``, где фигурирует ``drop_user_id``, переподвешиваются на ``keep_user_id``.

    Сначала ``referee_id`` (чтобы не оставить ссылок на удаляемого пользователя), затем
    ``user_id`` — иначе при ``ON DELETE CASCADE`` строки задач удалились бы вместе с ``drop``.
    """
    await session.execute(
        update(Task).where(Task.referee_id == drop_user_id).values(referee_id=keep_user_id),
    )
    await session.execute(
        update(Task).where(Task.user_id == drop_user_id).values(user_id=keep_user_id),
    )


async def merge_reassign_user_http_traces(
    session: AsyncSession,
    *,
    keep_user_id: int,
    drop_user_id: int,
) -> None:
    await session.execute(
        update(UserHttpRequestTrace)
        .where(UserHttpRequestTrace.user_id == drop_user_id)
        .values(user_id=keep_user_id),
    )


async def merge_subscription_devices_users(
    session: AsyncSession,
    *,
    keep_user_id: int,
    drop_user_id: int,
) -> None:
    """Перенести ``subscription_devices`` с ``drop`` на ``keep``; при коллизии ``fingerprint`` — одна строка."""
    rows = (
        await session.scalars(
            select(SubscriptionDevice).where(SubscriptionDevice.user_id == drop_user_id),
        )
    ).all()
    for row in rows:
        exist = (
            await session.scalars(
                select(SubscriptionDevice)
                .where(
                    SubscriptionDevice.user_id == keep_user_id,
                    SubscriptionDevice.fingerprint == row.fingerprint,
                )
                .limit(1),
            )
        ).first()
        if exist is None:
            row.user_id = keep_user_id
        else:
            if _dt_cmp(row.updated_at, exist.updated_at) > 0:
                exist.user_agent = row.user_agent or exist.user_agent
                exist.os = row.os or exist.os
                exist.hwid_raw = row.hwid_raw or exist.hwid_raw
                exist.updated_at = row.updated_at
                try:
                    exist.created_at = min(exist.created_at, row.created_at)
                except TypeError:
                    pass
            await session.delete(row)


async def merge_drop_user_into_keep(session: AsyncSession, keep: User, drop: User) -> None:
    """Перенести данные с ``drop`` на ``keep`` и удалить ``drop``.

    Переносятся: трафик по серверам (сумма по совпадающим дням и узлам), владелец личной
    реферальной ссылки, платежи, задачи (в т.ч. ``referee_id``), устройства подписки,
    HTTP-аудит; дата ``subscription_until`` — более поздняя из двух.
    """
    if keep.id == drop.id:
        return
    await merge_user_server_traffic(session, keep.id, drop.id)
    await merge_owned_referral_links(session, keep.id, drop.id)
    await merge_reassign_payments(session, keep_user_id=keep.id, drop_user_id=drop.id)
    await merge_reassign_tasks(session, keep_user_id=keep.id, drop_user_id=drop.id)
    await merge_reassign_user_http_traces(session, keep_user_id=keep.id, drop_user_id=drop.id)
    await merge_subscription_devices_users(session, keep_user_id=keep.id, drop_user_id=drop.id)
    keep.subscription_until = _later_subscription_date(keep.subscription_until, drop.subscription_until)
    await session.delete(drop)
    await session.flush()
