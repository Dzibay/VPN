import logging
from datetime import date, datetime
from typing import Annotated, Literal, cast as type_cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import and_, case, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.api.deps import (
    ReadonlySessionDep,
    SessionDep,
    StaffUserListMode,
    require_admin,
    require_referrals_staff,
    require_staff_user_list_access,
)
from app.database.operations import table_insert
from app.domain.user_traffic import user_server_traffic_latest_subquery
from app.models.server import Server
from app.models.user import User
from app.models.user_server_traffic import UserServerTraffic
from app.schemas.server_traffic import (
    UserTrafficByDayRow,
    UserTrafficByServersBundle,
    UserTrafficPerServerRow,
)
from app.schemas.users import (
    ExtendActiveSubscriptionsBody,
    ExtendActiveSubscriptionsResponse,
    UserCreate,
    UserListItem,
    UserRead,
    UserRegistrationByDateRow,
    UsersCountResponse,
    UserUpdate,
)
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.users")

router = APIRouter(
    prefix="/users",
    tags=["admin"],
)


def _normalize_account_role(raw: str | None) -> str:
    r = (raw or "client").strip()
    if r in ("client", "manager", "admin"):
        return r
    return "client"


def _user_rows_with_traffic(session: Session) -> list[tuple[User, int]]:
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
    stmt = (
        select(User, func.coalesce(traffic_agg.c.total_bytes, 0).label("total_traffic"))
        .outerjoin(traffic_agg, User.id == traffic_agg.c.uid)
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
    """
    По каждому календарному дню, где есть хотя бы один снимок по пользователю:
    сумма (up+down) последних строк на узел с traffic_date <= этого дня.
    """
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


@router.get(
    "/count",
    response_model=UsersCountResponse,
    dependencies=[Depends(require_admin)],
    summary="Число записей пользователей в базе данных",
)
async def users_count(session: ReadonlySessionDep) -> UsersCountResponse:
    total = session.scalar(select(func.count()).select_from(User))
    return UsersCountResponse(users_count=int(total or 0))


@router.get(
    "",
    response_model=list[UserListItem],
    summary=(
        "Список пользователей для административного и менеджерского интерфейса; "
        "токен подписки и UUID VLESS возвращаются только при доступе администратора"
    ),
)
async def list_users(
    session: ReadonlySessionDep,
    list_mode: Annotated[StaffUserListMode, Depends(require_staff_user_list_access)],
) -> list[UserListItem]:
    show_secrets = list_mode in ("open", "admin")
    rows = _user_rows_with_traffic(session)
    out: list[UserListItem] = []
    for user, total_raw in rows:
        try:
            total = int(total_raw or 0)
        except (TypeError, ValueError):
            total = 0
        if total < 0:
            total = 0
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
                referral_link_id=user.referral_link_id,
                token=(user.token if show_secrets else None),
                vless_uuid=(user.vless_uuid if show_secrets else None),
            ),
        )
    return out


@router.get(
    "/registrations-by-date",
    response_model=list[UserRegistrationByDateRow],
    dependencies=[Depends(require_referrals_staff)],
    summary="Число регистраций по календарным дням (UTC)",
)
async def users_registrations_by_date(
    session: ReadonlySessionDep,
) -> list[UserRegistrationByDateRow]:
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
            day_expr.label("registration_date"),
            func.count().label("cnt"),
            with_traffic_expr,
        )
        .select_from(User)
        .outerjoin(traffic_totals, User.id == traffic_totals.c.uid)
        .group_by(day_expr)
        .order_by(day_expr.desc().nulls_last())
    )
    rows = session.execute(stmt).all()
    out: list[UserRegistrationByDateRow] = []
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
            rd = None
        elif isinstance(rd_raw, datetime):
            rd = rd_raw.date()
        elif isinstance(rd_raw, date):
            rd = rd_raw
        else:
            rd = None
        out.append(
            UserRegistrationByDateRow(
                registration_date=rd,
                users_count=max(0, n),
                users_with_traffic_count=wt,
            ),
        )
    return out


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(require_admin)],
    summary="Создание пользователя; токен подписки и UUID генерируются на сервере",
)
async def create_user(
    body: UserCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
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
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким Telegram (telegram_id) уже существует",
        ) from e
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user


@router.post(
    "/extend-active-subscriptions",
    response_model=ExtendActiveSubscriptionsResponse,
    dependencies=[Depends(require_admin)],
    summary=(
        "Продление подписки на указанное число календарных дней для всех записей "
        "с активной конечной датой; пользователи без срока подписки не изменяются"
    ),
)
async def extend_active_subscriptions(
    body: ExtendActiveSubscriptionsBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
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
    if n:
        background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return ExtendActiveSubscriptionsResponse(updated_count=n)


@router.get(
    "/{user_id}/traffic-by-server",
    response_model=UserTrafficByServersBundle,
    dependencies=[Depends(require_admin)],
    summary="Трафик пользователя по узлам (данные из базы)",
)
async def user_traffic_by_server(
    user_id: int,
    session: ReadonlySessionDep,
) -> UserTrafficByServersBundle:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
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
    for server, up_raw, down_raw in rows:
        up = int(up_raw or 0)
        down = int(down_raw or 0)
        total_up += up
        total_down += down
        out.append(
            UserTrafficPerServerRow(
                server_id=server.id,
                name=server.name,
                host=server.host,
                port=server.port,
                country=server.country or "",
                is_active=server.is_active,
                provision_ready=server.provision_ready,
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


@router.get(
    "/{user_id}/traffic-by-day",
    response_model=list[UserTrafficByDayRow],
    dependencies=[Depends(require_admin)],
    summary="Накопительный трафик по календарным дням (UTC)",
)
async def user_traffic_by_day(
    user_id: int,
    session: ReadonlySessionDep,
) -> list[UserTrafficByDayRow]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user_traffic_cumulative_by_day_rows(session, user_id)


@router.delete(
    "/{user_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
    summary="Удаление пользователя и синхронизация списка клиентов на узлах",
)
async def delete_user(
    user_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    session.delete(user)
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_admin)],
    summary="Частичное обновление пользователя и синхронизация Xray на узлах",
)
async def patch_user(
    user_id: int,
    body: UserUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return user
    new_role = data.get("account_role")
    if new_role == "admin" and not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Нельзя назначить роль admin без пароля у пользователя",
        )
    for key, value in data.items():
        setattr(user, key, value)
    session.flush()
    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return user
