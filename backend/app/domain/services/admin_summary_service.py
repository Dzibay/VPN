from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.admin_summary import AdminSummaryResponse


def _to_decimal(v: object) -> Decimal:
    if v is None:
        return Decimal(0)
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v).replace(",", "."))


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100.0 / denominator, 2)


async def get_admin_summary(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
) -> AdminSummaryResponse:
    stmt = text("SELECT rpc_admin_summary(:p_from, :p_to) AS payload")
    row = (await session.execute(stmt, {"p_from": date_from, "p_to": date_to})).one()
    raw = row.payload if isinstance(row.payload, dict) else {}

    users_total = int(raw.get("users_total") or 0)
    active_users = int(raw.get("active_users") or 0)
    paying_users_total = int(raw.get("paying_users_total") or 0)
    payments_count = int(raw.get("payments_count") or 0)
    revenue_period = _to_decimal(raw.get("revenue_period"))

    avg_check = (
        (revenue_period / payments_count).quantize(Decimal("0.01"))
        if payments_count > 0
        else Decimal(0)
    )

    return AdminSummaryResponse(
        period_from=date_from,
        period_to=date_to,
        msk_today=raw.get("msk_today") or date_to,
        users_total=users_total,
        users_in_period=int(raw.get("users_in_period") or 0),
        active_users=active_users,
        active_users_pct=_pct(active_users, users_total),
        expiring_subscriptions=int(raw.get("expiring_subscriptions") or 0),
        expiring_paid=int(raw.get("expiring_paid") or 0),
        revenue_period=revenue_period,
        revenue_total=_to_decimal(raw.get("revenue_total")),
        avg_check=avg_check,
        payments_count=payments_count,
        avg_revenue_per_paying_user=_to_decimal(raw.get("avg_revenue_per_paying_user")),
        paying_users_total=paying_users_total,
        conversion_pct=_pct(paying_users_total, users_total),
    )
