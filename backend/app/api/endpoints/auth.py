from secrets import compare_digest

from fastapi import APIRouter, HTTPException

from app.core.admin_token import create_admin_jwt
from app.core.config import get_settings
from app.schemas.auth import AuthStatusResponse, LoginBody, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/status",
    response_model=AuthStatusResponse,
    summary="Нужна ли авторизация для админ-эндпоинтов",
)
async def auth_status() -> AuthStatusResponse:
    pwd = (get_settings().admin_panel_password or "").strip()
    return AuthStatusResponse(admin_auth_required=bool(pwd))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход в админку (пароль из env сервера)",
)
async def login(body: LoginBody) -> TokenResponse:
    pwd = (get_settings().admin_panel_password or "").strip()
    if not pwd:
        raise HTTPException(
            status_code=503,
            detail="Пароль админки не задан (ADMIN_PANEL_PASSWORD в .env)",
        )
    if not compare_digest(pwd, body.password):
        raise HTTPException(status_code=401, detail="Неверный пароль")
    settings = get_settings()
    try:
        token = create_admin_jwt(settings)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return TokenResponse(access_token=token)
