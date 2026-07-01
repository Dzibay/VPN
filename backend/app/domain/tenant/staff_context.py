"""Staff JWT claims в contextvars (для scope без явного X-Admin-Project)."""

from __future__ import annotations

from contextvars import ContextVar

from app.core.staff_token import StaffClaims

_current_staff: ContextVar[StaffClaims | None] = ContextVar("current_staff", default=None)


def set_current_staff(claims: StaffClaims | None) -> object:
    return _current_staff.set(claims)


def reset_current_staff(token: object) -> None:
    _current_staff.reset(token)  # type: ignore[arg-type]


def get_current_staff() -> StaffClaims | None:
    return _current_staff.get()
