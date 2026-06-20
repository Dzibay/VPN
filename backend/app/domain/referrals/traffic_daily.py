"""Суточный трафик пользователей, сгруппированный по реферальным токенам."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_today
from app.domain.models.referral_links import (
    ReferralTokensTrafficDailySummary,
    ReferralTokenTrafficDailySeries,
)
from app.domain.services.server_metrics_service import (
    _forward_fill_totals_on_grid,
    _inclusive_date_range,
)
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic


def _user_daily_deltas_on_grid(
    by_server: dict[int, list[tuple[date, int]]],
    grid: list[date],
    start: date,
) -> dict[date, int]:
    """Суточные дельты суммарного up+down пользователя по всем узлам."""
    if not by_server or not grid:
        return {}
    server_grids = {
        sid: _forward_fill_totals_on_grid(series, grid)
        for sid, series in by_server.items()
    }
    day_delta: dict[date, int] = defaultdict(int)
    for i in range(1, len(grid)):
        d = grid[i]
        if d < start:
            continue
        prev_total = sum(server_grids[sid][i - 1] for sid in server_grids)
        curr_total = sum(server_grids[sid][i] for sid in server_grids)
        day_delta[d] = max(0, curr_total - prev_total)
    return day_delta


def referral_tokens_traffic_daily_blocking(
    db: Session,
    *,
    days: int,
    min_registrations: int = 10,
) -> ReferralTokensTrafficDailySummary:
    """Суточные дельты up+down по токенам с registrations_count > min_registrations."""
    span = max(1, min(int(days), 366))
    threshold = max(0, int(min_registrations))
    today = utc_today()
    start = today - timedelta(days=span - 1)
    day_before_start = start - timedelta(days=1)
    grid = _inclusive_date_range(day_before_start, today)
    dates = _inclusive_date_range(start, today)
    if not grid:
        return ReferralTokensTrafficDailySummary(min_registrations=threshold)

    link_rows = db.execute(
        select(
            ReferralLink.id,
            ReferralLink.token,
            ReferralLink.registrations_count,
        )
        .where(ReferralLink.registrations_count > threshold)
        .order_by(ReferralLink.registrations_count.desc(), ReferralLink.id.asc()),
    ).all()
    if not link_rows:
        return ReferralTokensTrafficDailySummary(
            dates=dates,
            min_registrations=threshold,
        )

    link_ids = {int(r[0]) for r in link_rows}
    user_rows = db.execute(
        select(User.id, User.referral_link_id).where(User.referral_link_id.in_(link_ids)),
    ).all()
    user_to_link = {
        int(uid): int(rid)
        for uid, rid in user_rows
        if rid is not None and int(rid) in link_ids
    }
    user_ids = set(user_to_link.keys())

    by_user_server: dict[int, dict[int, list[tuple[date, int]]]] = defaultdict(
        lambda: defaultdict(list),
    )
    if user_ids:
        traffic_rows = db.execute(
            select(
                UserServerTraffic.user_id,
                UserServerTraffic.server_id,
                UserServerTraffic.traffic_date,
                (UserServerTraffic.up_bytes + UserServerTraffic.down_bytes).label("tot"),
            )
            .where(UserServerTraffic.user_id.in_(user_ids))
            .order_by(
                UserServerTraffic.user_id.asc(),
                UserServerTraffic.server_id.asc(),
                UserServerTraffic.traffic_date.asc(),
            ),
        ).all()
        for uid_raw, sid_raw, traffic_d, tot in traffic_rows:
            by_user_server[int(uid_raw)][int(sid_raw)].append(
                (traffic_d, int(tot or 0)),
            )

    by_link_delta: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for uid, link_id in user_to_link.items():
        by_server = by_user_server.get(uid)
        if not by_server:
            continue
        user_delta = _user_daily_deltas_on_grid(by_server, grid, start)
        for d, val in user_delta.items():
            by_link_delta[link_id][d] += val

    token_series: list[ReferralTokenTrafficDailySeries] = []
    for link_id_raw, token, reg_count in link_rows:
        link_id = int(link_id_raw)
        deltas = [int(by_link_delta[link_id].get(d, 0)) for d in dates]
        token_series.append(
            ReferralTokenTrafficDailySeries(
                referral_link_id=link_id,
                token=str(token),
                registrations_count=int(reg_count or 0),
                delta_bytes=deltas,
            ),
        )

    total_delta = [
        sum(int(s.delta_bytes[i]) for s in token_series)
        for i in range(len(dates))
    ]

    return ReferralTokensTrafficDailySummary(
        dates=dates,
        min_registrations=threshold,
        total_delta_bytes=total_delta,
        tokens=token_series,
    )
