"""Пользователи: идентификаторы, Xray-очередь, админские списки и аналитика."""

from __future__ import annotations

import logging
import uuid as uuid_lib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Literal, cast as type_cast

from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from sqlalchemy import and_, case, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.config import settings
from app.domain.models.server_traffic import (
    UserTrafficByDayRow,
    UserTrafficByServersBundle,
    UserTrafficPerServerRow,
)
from app.domain.models.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    UserCreate,
    UserListItem,
    UserStatsByDateRow,
    UsersCountResponse,
    UsersDailyStatsResponse,
    UserUpdate,
)
from app.domain.services.http_errors import HttpServiceError
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.infrastructure.cache import get_install_queue, get_redis
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.subscription_device import SubscriptionDevice
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic

log = logging.getLogger("app.users_service")

_SUBSCRIPTION_TOKEN_BYTES = 24

# RQ разрешает только [A-Za-z0-9_-]; двоеточия в id запрещены (rq.job.validate_job_id).
RQ_JOB_ID_SYNC_XRAY_ALL = "vpn_sync_xray_clients_all"

_ACTIVE_XRAY_SYNC_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.QUEUED,
        JobStatus.STARTED,
        JobStatus.SCHEDULED,
        JobStatus.DEFERRED,
    }
)

_TERMINAL_XRAY_SYNC_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.FINISHED,
        JobStatus.FAILED,
        JobStatus.STOPPED,
        JobStatus.CANCELED,
    }
)


def new_subscription_token() -> str:
    return token_urlsafe(_SUBSCRIPTION_TOKEN_BYTES)


def new_vless_uuid() -> str:
    return str(uuid_lib.uuid4())


def _rq_job_id_sync_xray_server(server_id: int) -> str:
    return f"vpn_sync_xray_clients_server_{int(server_id)}"


def _coalesce_enqueue(
    *,
    job_id: str,
    func_path: str,
    job_timeout: int,
    job_args: tuple[object, ...] = (),
) -> str:
    """
    Одна активная задача на стабильный job_id: не плодим дубликаты в RQ при наплыве запросов.

    Завершённые / упавшие задачи удаляются и можно поставить новую с тем же id.
    """
    conn = get_redis()
    q = get_install_queue()
    try:
        job = Job.fetch(job_id, connection=conn)
        st = job.get_status()
        if st in _ACTIVE_XRAY_SYNC_STATUSES:
            log.debug(
                "xray sync coalesce: пропуск, job_id=%s уже %s",
                job_id,
                st,
            )
            return job_id
        if st in _TERMINAL_XRAY_SYNC_STATUSES:
            job.delete()
        else:
            log.warning(
                "xray sync coalesce: неожиданный статус job_id=%s (%s), пересоздаём",
                job_id,
                st,
            )
            job.delete()
    except NoSuchJobError:
        pass

    q.enqueue(
        func_path,
        *job_args,
        job_id=job_id,
        job_timeout=job_timeout,
    )
    return job_id


def ensure_sync_xray_clients_all_servers_enqueued() -> str:
    """
    Полный sync inbound на всех provision_ready узлах.
    Идемпотентно относительно очереди: повторные вызовы не создают вторую активную задачу.
    """
    return _coalesce_enqueue(
        job_id=RQ_JOB_ID_SYNC_XRAY_ALL,
        func_path="app.worker.jobs.sync_xray_clients_all_servers",
        job_timeout=max(settings.provision_job_timeout, 600),
    )


def ensure_sync_xray_clients_to_server_enqueued(server_id: int) -> str:
    """Точечный sync на одном узле (каскад, ручной вызов API)."""
    sid = int(server_id)
    return _coalesce_enqueue(
        job_id=_rq_job_id_sync_xray_server(sid),
        func_path="app.worker.jobs.sync_xray_clients_to_server",
        job_timeout=max(settings.provision_subprocess_timeout, 300),
        job_args=(sid,),
    )


def enqueue_sync_xray_clients_all_servers() -> None:
    """Для BackgroundTasks: ошибки Redis только в лог (как раньше)."""
    try:
        ensure_sync_xray_clients_all_servers_enqueued()
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь синхронизацию Xray (Redis недоступен)",
            exc_info=True,
        )


def enqueue_sync_xray_clients_to_server(server_id: int) -> None:
    """Для каскада / внутренних вызовов: не бросает RedisError наружу."""
    try:
        ensure_sync_xray_clients_to_server_enqueued(server_id)
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь sync Xray для server_id=%s (Redis)",
            server_id,
            exc_info=True,
        )


def _normalize_account_role(raw: str | None) -> str:
    r = (raw or "client").strip()
    if r in ("client", "manager", "admin"):
        return r
    return "client"


def _user_rows_with_traffic(session: Session) -> list[tuple[User, int, int]]:
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
    return list(session.execute(stmt).all())


def _calendar_date(d_raw: date | datetime) -> date | None:
    if isinstance(d_raw, datetime):
        return d_raw.date()
    if isinstance(d_raw, date):
        return d_raw
    return None


def user_traffic_cumulative_by_day_rows(
    session: Session,
    user_id: int,
) -> list[UserTrafficByDayRow]:
    stmt = (
        select(
            UserServerTraffic.server_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
        )
        .where(UserServerTraffic.user_id == user_id)
        .order_by(UserServerTraffic.server_id.asc(), UserServerTraffic.traffic_date.asc())
    )
    rows_raw = session.execute(stmt).all()
    by_server: dict[int, list[tuple[date, int]]] = {}
    day_markers: set[date] = set()
    for sid_raw, td_raw, total_raw in rows_raw:
        cal = _calendar_date(td_raw)
        if cal is None:
            continue
        sid = int(sid_raw)
        tot = int(total_raw or 0)
        if tot < 0:
            tot = 0
        by_server.setdefault(sid, []).append((cal, tot))
        day_markers.add(cal)
    if not day_markers:
        return []
    servers = sorted(by_server.keys())
    indices = {sid: 0 for sid in servers}
    current = {sid: 0 for sid in servers}
    out: list[UserTrafficByDayRow] = []
    for d in sorted(day_markers):
        for sid in servers:
            series = by_server[sid]
            i = indices[sid]
            while i < len(series) and series[i][0] <= d:
                current[sid] = series[i][1]
                i += 1
            indices[sid] = i
        cumulative = sum(current.values())
        out.append(UserTrafficByDayRow(traffic_date=d, cumulative_bytes=cumulative))
    return out


def _traffic_active_count_by_date(
    session: Session,
    *,
    user_ids_filter: set[int] | None = None,
) -> dict[date, int]:
    stmt = (
        select(
            UserServerTraffic.user_id,
            UserServerTraffic.server_id,
            UserServerTraffic.traffic_date,
            UserServerTraffic.up_bytes + UserServerTraffic.down_bytes,
        )
        .order_by(
            UserServerTraffic.user_id.asc(),
            UserServerTraffic.server_id.asc(),
            UserServerTraffic.traffic_date.asc(),
        )
    )
    raw = session.execute(stmt).all()
    by_user: dict[int, dict[int, list[tuple[date, int]]]] = defaultdict(
        lambda: defaultdict(list),
    )
    all_dates: set[date] = set()
    for uid_raw, sid_raw, td_raw, tot_raw in raw:
        cal = _calendar_date(td_raw)
        if cal is None:
            continue
        tot = int(tot_raw or 0)
        if tot < 0:
            tot = 0
        uid = int(uid_raw)
        if user_ids_filter is not None and uid not in user_ids_filter:
            continue
        sid = int(sid_raw)
        by_user[uid][sid].append((cal, tot))
        all_dates.add(cal)
    if not all_dates:
        return {}
    min_d = min(all_dates)
    max_d = max(all_dates)
    day_list: list[date] = []
    d = min_d
    while d <= max_d:
        day_list.append(d)
        d += timedelta(days=1)

    user_states: dict[int, dict[str, object]] = {}
    for uid, servers_map in by_user.items():
        for sid in servers_map:
            servers_map[sid].sort(key=lambda x: x[0])
        user_states[uid] = {
            "idx": {sid: 0 for sid in servers_map},
            "cur": {sid: 0 for sid in servers_map},
            "prev_total": 0,
        }

    result: dict[date, int] = {}
    for cal_day in day_list:
        active = 0
        for uid, st in user_states.items():
            servers_map = by_user[uid]
            idx_map = st["idx"]
            cur_map = st["cur"]
            assert isinstance(idx_map, dict)
            assert isinstance(cur_map, dict)
            for sid, series in servers_map.items():
                i = int(idx_map[sid])
                while i < len(series) and series[i][0] <= cal_day:
                    cur_map[sid] = series[i][1]
                    i += 1
                idx_map[sid] = i
            total = int(sum(int(cur_map[sid]) for sid in servers_map))
            prev_total = int(st["prev_total"])
            if total > prev_total:
                active += 1
            st["prev_total"] = total
        result[cal_day] = active
    return result


def count_users_with_subscription_device(
    session: Session,
    referral_link_id: int | None,
) -> int:
    """Число пользователей с хотя бы одной записью в subscription_devices (опционально по referral_link_id)."""

    stmt = select(func.count(func.distinct(SubscriptionDevice.user_id))).select_from(
        SubscriptionDevice,
    ).join(User, User.id == SubscriptionDevice.user_id)
    if referral_link_id is not None:
        stmt = stmt.where(User.referral_link_id == referral_link_id)
    return int(session.scalar(stmt) or 0)


def active_users_count_for_utc_date(
    session: Session,
    cal_day: date,
    referral_link_id: int | None,
) -> int:
    """Столько же «активных», что и active_users_count в /api/users/daily-stats для календарного дня UTC."""

    filt: set[int] | None = None
    if referral_link_id is not None:
        ids_raw = session.scalars(
            select(User.id).where(User.referral_link_id == referral_link_id),
        ).all()
        filt = {int(i) for i in ids_raw}
    m = _traffic_active_count_by_date(session, user_ids_filter=filt)
    return int(m.get(cal_day, 0) or 0)


def _registration_counts_by_date(
    session: Session,
) -> dict[date | None, tuple[int, int]]:
    latest = user_server_traffic_latest_subquery()
    traffic_totals = (
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
    day_expr = cast(func.timezone("UTC", User.registered_at), Date)
    with_traffic_expr = func.sum(
        case(
            (func.coalesce(traffic_totals.c.total_bytes, 0) > 0, 1),
            else_=0,
        ),
    ).label("with_traffic_cnt")
    stmt = (
        select(
            day_expr.label("day_raw"),
            func.count().label("cnt"),
            with_traffic_expr,
        )
        .select_from(User)
        .outerjoin(traffic_totals, User.id == traffic_totals.c.uid)
        .group_by(day_expr)
    )
    rows = session.execute(stmt).all()
    out: dict[date | None, tuple[int, int]] = {}
    for rd_raw, cnt, wt_raw in rows:
        try:
            n = int(cnt or 0)
        except (TypeError, ValueError):
            n = 0
        try:
            wt = int(wt_raw or 0)
        except (TypeError, ValueError):
            wt = 0
        wt = max(0, min(wt, n))
        if rd_raw is None:
            rd: date | None = None
        elif isinstance(rd_raw, datetime):
            rd = rd_raw.date()
        elif isinstance(rd_raw, date):
            rd = rd_raw
        else:
            rd = None
        out[rd] = (max(0, n), wt)
    return out


def _first_subscription_device_users_by_utc_date(session: Session) -> dict[date, int]:
    stmt = (
        select(
            SubscriptionDevice.user_id,
            func.min(SubscriptionDevice.created_at).label("first_at"),
        )
        .group_by(SubscriptionDevice.user_id)
    )
    raw = session.execute(stmt).all()
    by_day: dict[date, int] = defaultdict(int)
    for _uid, first_at in raw:
        if first_at is None:
            continue
        if isinstance(first_at, datetime):
            if first_at.tzinfo is None:
                cal = first_at.replace(tzinfo=timezone.utc).date()
            else:
                cal = first_at.astimezone(timezone.utc).date()
        elif isinstance(first_at, date):
            cal = first_at
        else:
            continue
        by_day[cal] += 1
    return dict(by_day)


def stats_by_date_merged(session: Session) -> list[UserStatsByDateRow]:
    reg_map = _registration_counts_by_date(session)
    active_map = _traffic_active_count_by_date(session)
    dev_map = _first_subscription_device_users_by_utc_date(session)
    undated = reg_map.pop(None, None)
    date_keys = set(reg_map) | set(active_map) | set(dev_map)
    ordered = sorted(d for d in date_keys if d is not None)
    result: list[UserStatsByDateRow] = []
    for d in ordered:
        u, wt = reg_map.get(d, (0, 0))
        a = active_map.get(d, 0)
        dev_u = int(dev_map.get(d, 0) or 0)
        result.append(
            UserStatsByDateRow(
                stats_date=d,
                users_count=u,
                users_with_traffic_count=wt,
                active_users_count=a,
                subscription_devices_users_count=dev_u,
            ),
        )
    if undated is not None:
        u, wt = undated
        result.append(
            UserStatsByDateRow(
                stats_date=None,
                users_count=u,
                users_with_traffic_count=wt,
                active_users_count=0,
                subscription_devices_users_count=0,
            ),
        )
    return result


def users_count(session: Session) -> UsersCountResponse:
    total = session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


def staff_list_users(session: Session, *, show_secrets: bool) -> list[UserListItem]:
    rows = _user_rows_with_traffic(session)
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
                subscription_devices_count=dev_n,
                referral_link_id=user.referral_link_id,
                token=(user.token if show_secrets else None),
                vless_uuid=(user.vless_uuid if show_secrets else None),
            ),
        )
    return out


def users_daily_stats(session: Session) -> UsersDailyStatsResponse:
    return UsersDailyStatsResponse(stats_by_date=stats_by_date_merged(session))


def create_staff_user(session: Session, body: UserCreate) -> User:
    user = User(
        telegram_id=body.telegram_id,
        telegram_properties=body.telegram_properties,
        subscription_until=body.subscription_until,
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("create_user conflict: %s", e)
        raise HttpServiceError(
            409,
            "Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    return user


def extend_active_subscriptions(
    session: Session,
    body: ExtendActiveSubscriptionsBody,
) -> ExtendActiveSubscriptionsResponse:
    days = body.days
    stmt = (
        update(User)
        .where(
            User.subscription_until.isnot(None),
            User.subscription_until >= date.today(),
        )
        .values(subscription_until=User.subscription_until + days)
    )
    result = session.execute(stmt)
    n = int(result.rowcount or 0)
    return ExtendActiveSubscriptionsResponse(updated_count=n)


def user_traffic_by_servers_bundle(
    session: Session,
    user_id: int,
) -> UserTrafficByServersBundle:
    user = session.get(User, user_id)
    if user is None:
        raise HttpServiceError(404, "Пользователь не найден")
    latest = user_server_traffic_latest_subquery().alias("ut_latest")
    stmt = (
        select(Server, latest.c.up_bytes, latest.c.down_bytes)
        .select_from(Server)
        .outerjoin(
            latest,
            and_(
                latest.c.server_id == Server.id,
                latest.c.user_id == user_id,
            ),
        )
        .order_by(Server.id.asc())
    )
    rows = session.execute(stmt).all()
    out: list[UserTrafficPerServerRow] = []
    total_up = 0
    total_down = 0
    for srv, up_raw, down_raw in rows:
        up = int(up_raw or 0)
        down = int(down_raw or 0)
        total_up += up
        total_down += down
        out.append(
            UserTrafficPerServerRow(
                server_id=srv.id,
                name=srv.name,
                host=srv.host,
                port=srv.port,
                country=srv.country or "",
                is_active=srv.is_active,
                provision_ready=srv.provision_ready,
                up_bytes=up,
                down_bytes=down,
                total_bytes=up + down,
            ),
        )
    return UserTrafficByServersBundle(
        user_id=user.id,
        telegram_id=user.telegram_id,
        subscription_until=user.subscription_until,
        servers=out,
        total_up_bytes=total_up,
        total_down_bytes=total_down,
    )


def delete_staff_user(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise HttpServiceError(404, "Пользователь не найден")
    session.delete(user)


def patch_staff_user(session: Session, user_id: int, body: UserUpdate) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HttpServiceError(404, "Пользователь не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return user
    new_role = data.get("account_role")
    if new_role == "admin" and not user.password_hash:
        raise HttpServiceError(
            400,
            "Нельзя назначить роль admin без пароля у пользователя",
        )
    for key, value in data.items():
        setattr(user, key, value)
    session.flush()
    return user


def require_user_exists(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HttpServiceError(404, "Пользователь не найден")
    return user


def enqueue_sync_xray_clients_to_server(server_id: int) -> None:
    """Для каскада / внутренних вызовов: не бросает RedisError наружу."""
    try:
        ensure_sync_xray_clients_to_server_enqueued(server_id)
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь sync Xray для server_id=%s (Redis)",
            server_id,
            exc_info=True,
        )
