from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.admin_token import verify_admin_token
from app.core.config import get_settings
from app.database.session import get_db

SessionDep = Annotated[Session, Depends(get_db)]


def require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    pwd = (settings.admin_panel_password or "").strip()
    if not pwd:
        return
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Требуется вход в админку",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    if not token or not verify_admin_token(token, settings):
        raise HTTPException(
            status_code=401,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
