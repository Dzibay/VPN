import logging
from typing import Annotated, Any, Literal

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    BearerPrincipal,
    ReadonlySessionDep,
    SessionDep,
    get_bearer_principal_dep,
    require_telegram_bot_api_secret,
)
from app.core.access_token import create_access_token
from app.core.auth_env import normalize_email
from app.core.config import settings
from app.core.queue import get_redis
from app.core.passwords import hash_password, verify_password
from app.database.operations import table_insert
from app.domain.subscription import (
    subscription_until_after_registration,
    user_has_active_subscription,
)
from app.domain.user_traffic import user_traffic_totals
from app.models.referral_link import ReferralLink
from app.models.user import User
from app.schemas.account import (
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    TelegramAuthBody,
    TelegramSiteLinkCompleteBody,
    TelegramSiteLinkPreviewResponse,
    TelegramSiteLinkStartBody,
    TelegramSiteLinkStartResponse,
    TelegramSyncStartResponse,
    TelegramWebLinkBody,
    TelegramWebLinkResponse,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
    telegram_auth_has_profile_fields,
)
from app.schemas.auth import TelegramAuthTokenResponse, TokenResponse
from app.services.merge_telegram_account import merge_drop_user_into_keep
from app.services.referral_link_service import (
    increment_referral_counter,
    public_spa_base_url,
    telegram_bot_public_page_url,
)
from app.services.telegram_sync_token import (
    TelegramSyncRedisError,
    delete_site_cred_token,
    delete_sync_token,
    generate_sync_token_value,
    get_site_cred_user_id,
    get_sync_token_user_id,
    store_site_cred_token,
    store_sync_token,
    sync_start_payload,
)
from app.services.user_provision import (
    enqueue_sync_xray_clients_all_servers,
    new_subscription_token,
    new_vless_uuid,
)

log = logging.getLogger("app.auth")


def _jwt_role_for_user(user: User) -> Literal["user", "manager", "admin"]:
    """JWT-роль по users.account_role (client → user)."""
    ar = getattr(user, "account_role", None) or "client"
    if ar == "admin":
        return "admin"
    if ar == "manager":
        return "manager"
    return "user"


# Примеры ответа GET /api/auth/me в OpenAPI (ключи с null в JSON стандарте часто не показывают).
_AUTH_ME_OPENAPI_EXAMPLES: dict = {
    "user_with_email": {
        "summary": "Клиентская учётная запись (email и Telegram)",
        "description": "Типичный ответ после регистрации на сайте и привязки Telegram.",
        "value": {
            "role": "user",
            "id": 42,
            "email": "user@example.com",
            "telegram_id": 123456789,
            "telegram_properties": {
                "username": "ivan_dev",
                "first_name": "Ivan",
                "last_name": "Petrov",
                "topic_id": 2,
            },
            "subscription_until": "2026-12-31",
            "subscription_active": True,
            "subscription_token": "subscription-token-example",
            "subscription_open_clients": [
                {
                    "client_code": "happ",
                    "display_name": "Happ",
                    "store_platforms": ["android", "ios", "windows", "macos", "linux"],
                },
            ],
            "traffic_up_bytes": 1073741824,
            "traffic_down_bytes": 5368709120,
            "traffic_total_bytes": 6442450944,
            "registered_at": "2026-03-01T10:30:00+00:00",
        },
    },
    "user_telegram_only": {
        "summary": "Учётная запись только через Telegram",
        "value": {
            "role": "user",
            "id": 7,
            "telegram_id": 998877665,
            "telegram_properties": {
                "username": "daria_vpn",
                "first_name": "Daria",
            },
            "subscription_active": False,
            "subscription_token": "subscription-token-telegram",
            "subscription_open_clients": [],
        },
    },
    "admin": {
        "summary": "Администратор",
        "description": "Часть полей отсутствует или равна null; полный перечень см. в схеме ответа.",
        "value": {
            "role": "admin",
            "email": "admin@example.com",
            "registered_at": "2025-01-15T08:00:00+00:00",
            "subscription_active": False,
            "subscription_token": "",
        },
    },
}

router = APIRouter(prefix="/auth")


@router.post(
    "/login",
    response_model=TokenResponse,
    tags=["public"],
    summary="Аутентификация по email и паролю; ответ содержит JWT",
)
async def login(body: AccountLoginBody, session: ReadonlySessionDep) -> TokenResponse:
    email = normalize_email(str(body.email))
    stmt = select(User).where(User.email == email).limit(1)
    user = session.scalars(stmt).first()

    if user is not None:
        if not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        jwt_role = _jwt_role_for_user(user)
        try:
            token = create_access_token(settings, role=jwt_role, user_id=user.id)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return TokenResponse(access_token=token, role=jwt_role)

    raise HTTPException(status_code=401, detail="Неверный email или пароль")


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    tags=["public"],
    summary="Регистрация по email и паролю; ответ содержит JWT",
)
async def register(
    body: AccountRegisterBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    email = normalize_email(str(body.email))
    pwd_hash = hash_password(body.password)
    user = User(
        email=email,
        password_hash=pwd_hash,
        telegram_id=None,
        telegram_properties=None,
        subscription_until=subscription_until_after_registration(),
        token=new_subscription_token(),
        vless_uuid=new_vless_uuid(),
    )
    try:
        table_insert(session, user)
    except IntegrityError as e:
        log.warning("register conflict: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким email уже зарегистрирован",
        ) from e

    if body.referral_token:
        rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
        rlink = session.scalars(rstmt).first()
        if rlink is not None:
            user.referral_link_id = rlink.id
            increment_referral_counter(session, rlink.id, "registrations")
            session.flush()

    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    try:
        token = create_access_token(settings, role="user", user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=token, role="user")


@router.post(
    "/telegram",
    response_model=TelegramAuthTokenResponse,
    status_code=201,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Аутентификация и регистрация через Telegram (обязательный заголовок X-Telegram-Bot-Secret)",
)
async def telegram_auth(
    body: TelegramAuthBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramAuthTokenResponse:
    tid = body.telegram_id
    profile = merge_telegram_auth_profile(body, None)
    stmt = select(User).where(User.telegram_id == tid).limit(1)
    user = session.scalars(stmt).first()
    is_new_user = False
    if user is None:
        user = User(
            email=None,
            password_hash=None,
            telegram_id=tid,
            telegram_properties=profile,
            subscription_until=subscription_until_after_registration(),
            token=new_subscription_token(),
            vless_uuid=new_vless_uuid(),
        )
        try:
            table_insert(session, user)
        except IntegrityError as e:
            log.warning("telegram register conflict, refetch: %s", e)
            session.rollback()
            user = session.scalars(
                select(User).where(User.telegram_id == tid).limit(1)
            ).first()
            if user is None:
                raise HTTPException(
                    status_code=409,
                    detail="Не удалось создать или найти пользователя по telegram_id",
                ) from e
        else:
            is_new_user = True
            if body.referral_token:
                rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
                rlink = session.scalars(rstmt).first()
                if rlink is not None:
                    user.referral_link_id = rlink.id
                    increment_referral_counter(session, rlink.id, "clicks")
                    increment_referral_counter(session, rlink.id, "registrations")
                    session.flush()
            background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    elif telegram_auth_has_profile_fields(body):
        user.telegram_properties = merge_telegram_auth_profile(
            body,
            user.telegram_properties,
        )
        session.flush()

    try:
        jwt_role = _jwt_role_for_user(user)
        token = create_access_token(settings, role=jwt_role, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TelegramAuthTokenResponse(
        access_token=token,
        role=jwt_role,
        is_new_user=is_new_user,
    )


@router.post(
    "/telegram/link",
    response_model=TelegramWebLinkResponse,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Привязка Telegram к учётной записи по одноразовому токену из личного кабинета",
)
async def telegram_link_web_account(
    body: TelegramWebLinkBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TelegramWebLinkResponse:
    redis_conn = get_redis()
    key_part = body.link_token
    try:
        uid = get_sync_token_user_id(redis_conn, key_part)
    except TelegramSyncRedisError:
        raise HTTPException(status_code=503, detail="Redis недоступен") from None
    if uid is None:
        raise HTTPException(
            status_code=400,
            detail="Неверный или истёкший токен привязки",
        )

    target = session.get(User, uid)
    if target is None:
        raise HTTPException(status_code=400, detail="Пользователь по токену не найден")
    if target.telegram_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Этот аккаунт уже привязан к Telegram",
        )

    tid = body.telegram_id
    auth_fragment = TelegramAuthBody(
        telegram_id=tid,
        username=body.username,
        first_name=body.first_name,
        last_name=body.last_name,
        topic_id=body.topic_id,
    )

    stmt = select(User).where(User.telegram_id == tid).limit(1)
    other = session.scalars(stmt).first()

    merged = False
    telegram_props_base: dict[str, Any] | None = None
    if other is not None and other.id != target.id:
        if other.account_role not in ("client", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Учётная запись с этим Telegram имеет недопустимую роль для объединения",
            )
        if target.account_role not in ("client", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Целевой аккаунт не поддерживает объединение с дубликатом Telegram",
            )
        telegram_props_base = (
            dict(other.telegram_properties) if other.telegram_properties else {}
        )
        merge_drop_user_into_keep(session, target, other)
        merged = True

    profile = merge_telegram_auth_profile(auth_fragment, telegram_props_base)

    target.telegram_id = tid
    target.telegram_properties = profile
    session.flush()

    try:
        delete_sync_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram link: не удалось удалить одноразовый токен из Redis")

    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)
    return TelegramWebLinkResponse(
        status="merged" if merged else "linked",
        user_id=int(target.id),
    )


def _telegram_site_link_token_trim(raw: str) -> str:
    s = raw.strip()
    return s.replace(" ", "")


def _resolve_site_cred_user_id(redis_conn, raw_token: str) -> tuple[int, str]:
    """
    Нормализует token из query или тела, достаёт user_id из Redis (vpn:tg_site_cred:).
    Возвращает (user_id, key_part) — key_part нужен для delete_site_cred_token после успеха.
    """
    key_part = _telegram_site_link_token_trim(raw_token)
    if len(key_part) < 4:
        raise HTTPException(status_code=400, detail="Некорректный токен")
    try:
        uid = get_site_cred_user_id(redis_conn, key_part)
    except TelegramSyncRedisError:
        raise HTTPException(status_code=503, detail="Redis недоступен") from None
    if uid is None:
        raise HTTPException(
            status_code=404,
            detail="Ссылка недействительна или истекла. Запросите новую в боте.",
        )
    return uid, key_part


def _user_can_add_credentials_from_site(user: User) -> tuple[bool, str | None]:
    if user.account_role == "admin":
        return False, "Недопустимо для аккаунта администратора"
    mail = getattr(user, "email", None) or ""
    if str(mail).strip():
        return False, "На этом аккаунте уже указан email. Входите через сайт с паролём."
    if user.telegram_id is None:
        return False, "На аккаунте не указан Telegram"
    return True, None


@router.post(
    "/telegram/site-link/start",
    response_model=TelegramSiteLinkStartResponse,
    tags=["telegram"],
    dependencies=[Depends(require_telegram_bot_api_secret)],
    summary="Ссылка на сайт: форма привязки email/пароля или вход в кабинет по JWT (поля site_url и has_account)",
)
async def telegram_site_link_start(
    body: TelegramSiteLinkStartBody,
    session: ReadonlySessionDep,
) -> TelegramSiteLinkStartResponse:
    stmt = select(User).where(User.telegram_id == body.telegram_id).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь с таким Telegram не найден. Запустите бота и войдите в аккаунт.",
        )

    if user.account_role == "admin":
        raise HTTPException(
            status_code=409,
            detail="Недопустимо для аккаунта администратора",
        )

    mail = (getattr(user, "email", None) or "").strip()
    if mail and user.password_hash:
        base = public_spa_base_url(settings)
        if not base:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Не задан публичный URL SPA: задайте SITE_ADRESS в окружении (полный URL или host[:port])."
                ),
            )
        jwt_role = _jwt_role_for_user(user)
        try:
            token = create_access_token(settings, role=jwt_role, user_id=user.id)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        site_url = f"{base}/cabinet#tg_sso_token={token}"
        return TelegramSiteLinkStartResponse(site_url=site_url, has_account=True)

    ok, reason = _user_can_add_credentials_from_site(user)
    if not ok:
        raise HTTPException(status_code=409, detail=reason or "Нельзя добавить данные сайта для этого аккаунта")

    base = public_spa_base_url(settings)
    if not base:
        raise HTTPException(
            status_code=503,
            detail=(
                "Не задан публичный URL SPA: задайте SITE_ADRESS в окружении (полный URL или host[:port])."
            ),
        )

    token_val = generate_sync_token_value()
    try:
        store_site_cred_token(get_redis(), token_val, int(user.id))
    except TelegramSyncRedisError:
        raise HTTPException(status_code=503, detail="Redis недоступен") from None

    site_url = f"{base}/link-from-telegram?token={quote(token_val, safe='')}"
    return TelegramSiteLinkStartResponse(site_url=site_url, has_account=False)


@router.get(
    "/telegram/site-link/preview",
    response_model=TelegramSiteLinkPreviewResponse,
    tags=["public"],
    summary="Данные Telegram по одноразовому token из URL (до отправки формы)",
)
async def telegram_site_link_preview(
    session: ReadonlySessionDep,
    token: str = Query(
        ...,
        min_length=1,
        max_length=96,
        description="Параметр token из URL",
    ),
) -> TelegramSiteLinkPreviewResponse:
    redis_conn = get_redis()
    uid, _ = _resolve_site_cred_user_id(redis_conn, token)

    user = session.get(User, uid)
    if user is None or user.telegram_id is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    ok, _ = _user_can_add_credentials_from_site(user)
    return TelegramSiteLinkPreviewResponse(
        telegram_id=int(user.telegram_id),
        telegram_properties=user.telegram_properties,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        can_add_credentials=ok,
    )


@router.post(
    "/telegram/site-link/complete",
    response_model=TokenResponse,
    tags=["public"],
    summary=(
        "По одноразовому token: новый email на Telegram-аккаунт либо объединение с "
        "существующим email при верном пароле (merge_drop_user_into_keep)"
    ),
)
async def telegram_site_link_complete(
    body: TelegramSiteLinkCompleteBody,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TokenResponse:
    redis_conn = get_redis()
    uid, key_part = _resolve_site_cred_user_id(redis_conn, body.link_token)

    tg_user = session.get(User, uid)
    if tg_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    ok, reason = _user_can_add_credentials_from_site(tg_user)
    if not ok:
        raise HTTPException(status_code=409, detail=reason or "Нельзя выполнить операцию")

    email_norm = normalize_email(str(body.email))
    stmt_existing = select(User).where(User.email == email_norm).limit(1)
    existing = session.scalars(stmt_existing).first()

    winner: User
    if existing is None:
        if len(body.password.encode("utf-8")) > 72:
            raise HTTPException(status_code=400, detail="Пароль слишком длинный для системы входа")
        if len(str(body.password)) < 8:
            raise HTTPException(
                status_code=400,
                detail="Пароль должен содержать не менее 8 символов",
            )
        tg_user.email = email_norm
        tg_user.password_hash = hash_password(body.password)
        try:
            session.flush()
        except IntegrityError as e:
            session.rollback()
            log.warning("telegram site-link complete conflict: %s", e)
            raise HTTPException(
                status_code=409,
                detail="Пользователь с таким email уже зарегистрирован",
            ) from e
        winner = tg_user
    else:
        if existing.id == tg_user.id:
            raise HTTPException(
                status_code=500,
                detail="Несогласованное состояние учётной записи",
            )
        if not getattr(existing, "password_hash", None):
            raise HTTPException(
                status_code=403,
                detail=(
                    "У аккаунта с этим email не задан пароль для входа на сайте. "
                    "Восстановите доступ или напишите в поддержку."
                ),
            )
        if not verify_password(body.password, existing.password_hash):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        if existing.telegram_id is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Аккаунт с этим email уже привязан к Telegram. "
                    "Войдите на сайт с паролем."
                ),
            )
        if existing.account_role not in ("client", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Учётная запись с этим email не поддерживает объединение",
            )
        if tg_user.account_role not in ("client", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Telegram-аккаунт не поддерживает объединение",
            )

        tid = tg_user.telegram_id
        tprops = (
            dict(tg_user.telegram_properties) if tg_user.telegram_properties else None
        )
        try:
            merge_drop_user_into_keep(session, existing, tg_user)
            existing.telegram_id = tid
            existing.telegram_properties = tprops
            session.flush()
        except IntegrityError as e:
            session.rollback()
            log.warning("telegram site-link merge integrity: %s", e)
            raise HTTPException(
                status_code=409,
                detail="Не удалось объединить учётные записи (конфликт данных). Попробуйте позже или обратитесь в поддержку.",
            ) from e
        winner = existing

    try:
        delete_site_cred_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram site-link: не удалось удалить токен из Redis")

    background_tasks.add_task(enqueue_sync_xray_clients_all_servers)

    jwt_role = _jwt_role_for_user(winner)
    try:
        jwt = create_access_token(settings, role=jwt_role, user_id=winner.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(access_token=jwt, role=jwt_role)


@router.post(
    "/me/telegram-sync-start",
    response_model=TelegramSyncStartResponse,
    tags=["user"],
    summary="Одноразовая deep link-ссылка на бота (t.me/…?start=…) для привязки Telegram",
)
async def telegram_sync_start(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> TelegramSyncStartResponse:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail="Нужна авторизация под пользователем")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if user.telegram_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Telegram уже привязан к этому аккаунту",
        )

    base = telegram_bot_public_page_url(settings)
    if not base:
        raise HTTPException(
            status_code=503,
            detail="TELEGRAM_BOT_USERNAME не задан — ссылка на бота недоступна",
        )

    token_val = generate_sync_token_value()
    try:
        store_sync_token(get_redis(), token_val, int(user.id))
    except TelegramSyncRedisError:
        raise HTTPException(
            status_code=503,
            detail="Не удалось сохранить токен привязки (проверьте Redis)",
        ) from None

    payload = sync_start_payload(token_val)
    deep = f"{base}?start={quote(payload, safe='')}"
    return TelegramSyncStartResponse(telegram_deep_link=deep)


@router.get(
    "/me",
    response_model=AccountMeResponse,
    tags=["user"],
    summary="Профиль текущего пользователя по JWT",
    responses={
        200: {
            "description": "Данные учётной записи",
            "content": {
                "application/json": {
                    "examples": _AUTH_ME_OPENAPI_EXAMPLES,
                }
            },
        }
    },
)
async def me(
    session: ReadonlySessionDep,
    principal: Annotated[BearerPrincipal, Depends(get_bearer_principal_dep)],
) -> AccountMeResponse:
    if principal.role == "admin":
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="Недействительный токен")
        user = session.get(User, principal.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        if user.account_role != "admin":
            raise HTTPException(status_code=401, detail="Недействительный токен")
        up_b, down_b, total_b = user_traffic_totals(session, user.id)
        return AccountMeResponse(
            role="admin",
            id=user.id,
            email=user.email,
            telegram_id=user.telegram_id,
            telegram_properties=user.telegram_properties,
            telegram_bot_page_url=telegram_bot_public_page_url(settings),
            registered_at=user.registered_at,
            subscription_until=user.subscription_until,
            subscription_active=user_has_active_subscription(user),
            subscription_token=user.token,
            subscription_open_clients=build_subscription_open_client_items(),
            traffic_up_bytes=up_b,
            traffic_down_bytes=down_b,
            traffic_total_bytes=total_b,
        )
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if not user.email and not user.telegram_id:
        raise HTTPException(
            status_code=500,
            detail="У записи нет ни email, ни telegram_id",
        )
    up_b, down_b, total_b = user_traffic_totals(session, user.id)
    api_role = "manager" if principal.role == "manager" else "user"
    return AccountMeResponse(
        role=api_role,
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        telegram_properties=user.telegram_properties,
        telegram_bot_page_url=telegram_bot_public_page_url(settings),
        registered_at=user.registered_at,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        subscription_token=user.token,
        subscription_open_clients=build_subscription_open_client_items(),
        traffic_up_bytes=up_b,
        traffic_down_bytes=down_b,
        traffic_total_bytes=total_b,
    )
