from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.admin_token import verify_admin_token
from app.core.config import get_settings
from app.core.user_token import verify_user_token_user_id
from app.database.session import get_db
from app.models.user import User

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


def get_current_user_dep(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    settings = get_settings()
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    user_id = verify_user_token_user_id(token, settings)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
