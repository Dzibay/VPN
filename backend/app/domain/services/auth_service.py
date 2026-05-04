"""Авторизация и Telegram: слияние учёток, одноразовые токены Redis, сценарии входа и /auth/me."""

from __future__ import annotations

import logging
import secrets
import string
from datetime import date
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.access_token import create_access_token
from app.core.auth_env import normalize_email
from app.core.dependencies import BearerPrincipal
from app.core.passwords import hash_password, verify_password
from app.domain.models.auth import (
    AccountChangePasswordBody,
    AccountLoginBody,
    AccountMeResponse,
    AccountRegisterBody,
    SubscriptionConnectionItem,
    TelegramAuthBody,
    TelegramAuthTokenResponse,
    TelegramSiteLinkCompleteBody,
    TelegramSiteLinkPreviewResponse,
    TelegramSiteLinkStartBody,
    TelegramSiteLinkStartResponse,
    TelegramSyncStartResponse,
    TelegramWebLinkBody,
    TelegramWebLinkResponse,
    TokenResponse,
    build_subscription_open_client_items,
    merge_telegram_auth_profile,
    telegram_auth_has_profile_fields,
)
from app.domain.services.http_errors import HttpServiceError
from app.domain.services.referral_links_service import (
    get_user_owned_referral_link,
    increment_referral_counter,
    public_spa_base_url,
    telegram_bot_public_page_url,
)
from app.domain.services.subscription_service import (
    effective_subscription_device_limit,
    list_subscription_connection_records,
)
from app.domain.services.users_service import new_subscription_token, new_vless_uuid
from app.domain.subscription import subscription_until_after_registration, user_has_active_subscription
from app.domain.user_traffic import user_traffic_totals
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic

if TYPE_CHECKING:
    from redis import Redis

log = logging.getLogger("app.auth_service")
_TOKEN_ALPHABET = string.ascii_letters + string.digits + "_"
_TOKEN_LEN = 32
_TTL_SEC = 900
_KEY_PREFIX = "vpn:tg_sync:"
_SITE_CRED_PREFIX = "vpn:tg_site_cred:"


class TelegramSyncRedisError(Exception):
    """Ошибка записи/чтения одноразового токена Telegram в Redis."""


def _later_subscription(a: date | None, b: date | None) -> date | None:
    """Дата окончания подписки после слияния двух учёток: самая поздняя из двух
    (больше календарных дней доступа; пример: +10 дней vs +14 дней → остаётся +14).
    """
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def merge_user_server_traffic(session: Session, keep_user_id: int, drop_user_id: int) -> None:
    rows = session.scalars(
        select(UserServerTraffic).where(UserServerTraffic.user_id == drop_user_id),
    ).all()
    for row in rows:
        exist = session.get(
            UserServerTraffic,
            {
                "user_id": keep_user_id,
                "server_id": row.server_id,
                "traffic_date": row.traffic_date,
            },
        )
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
        session.delete(row)


def merge_owned_referral_links(session: Session, keep_user_id: int, drop_user_id: int) -> None:
    la = get_user_owned_referral_link(session, keep_user_id)
    lb = get_user_owned_referral_link(session, drop_user_id)
    if lb is None:
        return
    if la is None:
        lb.owner_user_id = keep_user_id
        session.flush()
        return
    la.clicks_count += lb.clicks_count
    la.registrations_count += lb.registrations_count
    la.payments_count += lb.payments_count
    session.delete(lb)
    session.flush()


def merge_drop_user_into_keep(session: Session, keep: User, drop: User) -> None:
    """
    Переносит трафик и личную реферальную ссылку с drop на keep, затем удаляет drop.

    ``subscription_until`` у keep становится более поздней из двух дат (максимум остатка подписки).
    """
    if keep.id == drop.id:
        return
    merge_user_server_traffic(session, keep.id, drop.id)
    merge_owned_referral_links(session, keep.id, drop.id)
    keep.subscription_until = _later_subscription(keep.subscription_until, drop.subscription_until)
    session.delete(drop)
    session.flush()


def generate_sync_token_value() -> str:
    """Случайная часть для deep link (только символы, разрешённые Telegram в /start)."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


def sync_start_payload(token_value: str) -> str:
    """Значение параметра ?start= для бота (не длиннее 64 символов)."""
    return f"link_{token_value}"


def _setex_user_mapping(redis: Redis, full_key: str, user_id: int) -> None:
    try:
        redis.setex(full_key, _TTL_SEC, str(int(user_id)))
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def _get_mapping_user_id(redis: Redis, full_key: str) -> int | None:
    try:
        raw = redis.get(full_key)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _delete_mapping(redis: Redis, full_key: str) -> None:
    try:
        redis.delete(full_key)
    except RedisError as e:
        raise TelegramSyncRedisError(str(e)) from e


def store_sync_token(redis: Redis, token_value: str, user_id: int) -> None:
    _setex_user_mapping(redis, _KEY_PREFIX + token_value, user_id)


def get_sync_token_user_id(redis: Redis, token_value: str) -> int | None:
    return _get_mapping_user_id(redis, _KEY_PREFIX + token_value)


def delete_sync_token(redis: Redis, token_value: str) -> None:
    _delete_mapping(redis, _KEY_PREFIX + token_value)


def store_site_cred_token(redis: Redis, token_value: str, user_id: int) -> None:
    """Связь одноразового токена (URL на сайт) с internal user_id."""
    _setex_user_mapping(redis, _SITE_CRED_PREFIX + token_value, user_id)


def get_site_cred_user_id(redis: Redis, token_value: str) -> int | None:
    return _get_mapping_user_id(redis, _SITE_CRED_PREFIX + token_value)


def delete_site_cred_token(redis: Redis, token_value: str) -> None:
    _delete_mapping(redis, _SITE_CRED_PREFIX + token_value)


def jwt_role_for_user(user: User) -> Literal["user", "manager", "admin"]:
    ar = getattr(user, "account_role", None) or "client"
    if ar == "admin":
        return "admin"
    if ar == "manager":
        return "manager"
    return "user"


def _access_token_or_http(cfg: Settings, *, role: str, user_id: int) -> str:
    try:
        return create_access_token(cfg, role=role, user_id=user_id)
    except ValueError as e:
        raise HttpServiceError(503, str(e)) from e


def telegram_site_link_token_trim(raw: str) -> str:
    return str(raw).strip().replace(" ", "")


def resolve_site_cred_user_id(redis: object, raw_token: str) -> tuple[int, str]:
    key_part = telegram_site_link_token_trim(raw_token)
    if len(key_part) < 4:
        raise HttpServiceError(400, "Некорректный токен")
    try:
        uid = get_site_cred_user_id(redis, key_part)
    except TelegramSyncRedisError:
        raise HttpServiceError(503, "Redis недоступен") from None
    if uid is None:
        raise HttpServiceError(
            404,
            "Ссылка недействительна или истекла. Запросите новую в боте.",
        )
    return uid, key_part


def user_can_add_credentials_from_site(user: User) -> tuple[bool, str | None]:
    if user.account_role == "admin":
        return False, "Недопустимо для аккаунта администратора"
    mail = getattr(user, "email", None) or ""
    if str(mail).strip():
        return False, "На этом аккаунте уже указан email. Входите через сайт с паролём."
    if user.telegram_id is None:
        return False, "На аккаунте не указан Telegram"
    return True, None


def login_with_password(session: Session, body: AccountLoginBody, cfg: Settings) -> TokenResponse:
    email = normalize_email(str(body.email))
    user = session.scalars(select(User).where(User.email == email).limit(1)).first()
    if user is None:
        raise HttpServiceError(401, "Неверный email или пароль")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HttpServiceError(401, "Неверный email или пароль")
    jwt_role = jwt_role_for_user(user)
    token = _access_token_or_http(cfg, role=jwt_role, user_id=user.id)
    return TokenResponse(access_token=token, role=jwt_role)


def register_with_email(session: Session, body: AccountRegisterBody, cfg: Settings) -> TokenResponse:
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
        raise HttpServiceError(409, "Пользователь с таким email уже зарегистрирован") from e

    if body.referral_token:
        rstmt = select(ReferralLink).where(ReferralLink.token == body.referral_token).limit(1)
        rlink = session.scalars(rstmt).first()
        if rlink is not None:
            user.referral_link_id = rlink.id
            increment_referral_counter(session, rlink.id, "registrations")
            session.flush()

    token = _access_token_or_http(cfg, role="user", user_id=user.id)
    return TokenResponse(access_token=token, role="user")


def telegram_authenticate(
    session: Session,
    body: TelegramAuthBody,
    cfg: Settings,
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
            user = session.scalars(select(User).where(User.telegram_id == tid).limit(1)).first()
            if user is None:
                raise HttpServiceError(
                    409,
                    "Не удалось создать или найти пользователя по telegram_id",
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
    elif telegram_auth_has_profile_fields(body):
        user.telegram_properties = merge_telegram_auth_profile(body, user.telegram_properties)
        session.flush()

    jwt_role = jwt_role_for_user(user)
    token = _access_token_or_http(cfg, role=jwt_role, user_id=user.id)
    return TelegramAuthTokenResponse(
        access_token=token,
        role=jwt_role,
        is_new_user=is_new_user,
    )


def telegram_link_web_account(
    session: Session,
    body: TelegramWebLinkBody,
    redis_conn: object,
    cfg: Settings,
) -> TelegramWebLinkResponse:
    key_part = body.link_token
    try:
        uid = get_sync_token_user_id(redis_conn, key_part)
    except TelegramSyncRedisError:
        raise HttpServiceError(503, "Redis недоступен") from None
    if uid is None:
        raise HttpServiceError(400, "Неверный или истёкший токен привязки")

    target = session.get(User, uid)
    if target is None:
        raise HttpServiceError(400, "Пользователь по токену не найден")
    if target.telegram_id is not None:
        raise HttpServiceError(409, "Этот аккаунт уже привязан к Telegram")

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
            raise HttpServiceError(
                403,
                "Учётная запись с этим Telegram имеет недопустимую роль для объединения",
            )
        if target.account_role not in ("client", "manager"):
            raise HttpServiceError(
                403,
                "Целевой аккаунт не поддерживает объединение с дубликатом Telegram",
            )
        telegram_props_base = dict(other.telegram_properties) if other.telegram_properties else {}
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

    return TelegramWebLinkResponse(status="merged" if merged else "linked", user_id=int(target.id))


def telegram_site_link_start(
    session: Session,
    body: TelegramSiteLinkStartBody,
    redis_conn: object,
    cfg: Settings,
) -> TelegramSiteLinkStartResponse:
    stmt = select(User).where(User.telegram_id == body.telegram_id).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        raise HttpServiceError(
            404,
            "Пользователь с таким Telegram не найден. Запустите бота и войдите в аккаунт.",
        )

    if user.account_role == "admin":
        raise HttpServiceError(409, "Недопустимо для аккаунта администратора")

    mail = (getattr(user, "email", None) or "").strip()
    if mail and user.password_hash:
        base = public_spa_base_url(cfg)
        if not base:
            raise HttpServiceError(
                503,
                "Не задан публичный URL SPA: задайте SITE_ADRESS в окружении (полный URL или host[:port]).",
            )
        jwt_role = jwt_role_for_user(user)
        token = _access_token_or_http(cfg, role=jwt_role, user_id=user.id)
        site_url = f"{base}/cabinet#tg_sso_token={token}"
        return TelegramSiteLinkStartResponse(site_url=site_url, has_account=True)

    ok, reason = user_can_add_credentials_from_site(user)
    if not ok:
        raise HttpServiceError(409, reason or "Нельзя добавить данные сайта для этого аккаунта")

    base = public_spa_base_url(cfg)
    if not base:
        raise HttpServiceError(
            503,
            "Не задан публичный URL SPA: задайте SITE_ADRESS в окружении (полный URL или host[:port]).",
        )

    token_val = generate_sync_token_value()
    try:
        store_site_cred_token(redis_conn, token_val, int(user.id))
    except TelegramSyncRedisError:
        raise HttpServiceError(503, "Redis недоступен") from None

    site_url = f"{base}/link-from-telegram?token={quote(token_val, safe='')}"
    return TelegramSiteLinkStartResponse(site_url=site_url, has_account=False)


def telegram_site_link_preview_response(
    session: Session,
    redis_conn: object,
    raw_token: str,
    cfg: Settings,
) -> TelegramSiteLinkPreviewResponse:
    uid, _ = resolve_site_cred_user_id(redis_conn, raw_token)
    user = session.get(User, uid)
    if user is None or user.telegram_id is None:
        raise HttpServiceError(404, "Пользователь не найден")

    ok, _ = user_can_add_credentials_from_site(user)
    return TelegramSiteLinkPreviewResponse(
        telegram_id=int(user.telegram_id),
        telegram_properties=user.telegram_properties,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user),
        can_add_credentials=ok,
    )


def telegram_site_link_complete(
    session: Session,
    body: TelegramSiteLinkCompleteBody,
    redis_conn: object,
    cfg: Settings,
) -> TokenResponse:
    uid, key_part = resolve_site_cred_user_id(redis_conn, body.link_token)

    tg_user = session.get(User, uid)
    if tg_user is None:
        raise HttpServiceError(404, "Пользователь не найден")

    ok, reason = user_can_add_credentials_from_site(tg_user)
    if not ok:
        raise HttpServiceError(409, reason or "Нельзя выполнить операцию")

    email_norm = normalize_email(str(body.email))
    stmt_existing = select(User).where(User.email == email_norm).limit(1)
    existing = session.scalars(stmt_existing).first()

    winner: User
    if existing is None:
        if len(body.password.encode("utf-8")) > 72:
            raise HttpServiceError(400, "Пароль слишком длинный для системы входа")
        if len(str(body.password)) < 8:
            raise HttpServiceError(400, "Пароль должен содержать не менее 8 символов")
        tg_user.email = email_norm
        tg_user.password_hash = hash_password(body.password)
        try:
            session.flush()
        except IntegrityError as e:
            session.rollback()
            log.warning("telegram site-link complete conflict: %s", e)
            raise HttpServiceError(409, "Пользователь с таким email уже зарегистрирован") from e
        winner = tg_user
    else:
        if existing.id == tg_user.id:
            raise HttpServiceError(500, "Несогласованное состояние учётной записи")
        if not getattr(existing, "password_hash", None):
            raise HttpServiceError(
                403,
                "У аккаунта с этим email не задан пароль для входа на сайте. "
                "Восстановите доступ или напишите в поддержку.",
            )
        if not verify_password(body.password, existing.password_hash):
            raise HttpServiceError(401, "Неверный email или пароль")
        if existing.telegram_id is not None:
            raise HttpServiceError(
                409,
                "Аккаунт с этим email уже привязан к Telegram. Войдите на сайт с паролем.",
            )
        if existing.account_role not in ("client", "manager"):
            raise HttpServiceError(403, "Учётная запись с этим email не поддерживает объединение")
        if tg_user.account_role not in ("client", "manager"):
            raise HttpServiceError(403, "Telegram-аккаунт не поддерживает объединение")

        tid = tg_user.telegram_id
        tprops = dict(tg_user.telegram_properties) if tg_user.telegram_properties else None
        try:
            merge_drop_user_into_keep(session, existing, tg_user)
            existing.telegram_id = tid
            existing.telegram_properties = tprops
            session.flush()
        except IntegrityError as e:
            session.rollback()
            log.warning("telegram site-link merge integrity: %s", e)
            raise HttpServiceError(
                409,
                "Не удалось объединить учётные записи (конфликт данных). Попробуйте позже или обратитесь в поддержку.",
            ) from e
        winner = existing

    try:
        delete_site_cred_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram site-link: не удалось удалить токен из Redis")

    jwt_role = jwt_role_for_user(winner)
    jwt = _access_token_or_http(cfg, role=jwt_role, user_id=winner.id)
    return TokenResponse(access_token=jwt, role=jwt_role)


def telegram_sync_start_link(session: Session, principal: BearerPrincipal, redis_conn: object, cfg: Settings) -> TelegramSyncStartResponse:
    if principal.user_id is None:
        raise HttpServiceError(401, "Нужна авторизация под пользователем")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HttpServiceError(401, "Пользователь не найден")
    if user.telegram_id is not None:
        raise HttpServiceError(409, "Telegram уже привязан к этому аккаунту")

    base = telegram_bot_public_page_url(cfg)
    if not base:
        raise HttpServiceError(503, "TELEGRAM_BOT_USERNAME не задан — ссылка на бота недоступна")

    token_val = generate_sync_token_value()
    try:
        store_sync_token(redis_conn, token_val, int(user.id))
    except TelegramSyncRedisError:
        raise HttpServiceError(503, "Не удалось сохранить токен привязки (проверьте Redis)") from None

    payload = sync_start_payload(token_val)
    deep = f"{base}?start={quote(payload, safe='')}"
    return TelegramSyncStartResponse(telegram_deep_link=deep)


def account_me(session: Session, principal: BearerPrincipal, cfg: Settings) -> AccountMeResponse:
    def response_for(user: User, *, role: str) -> AccountMeResponse:
        up_b, down_b, total_b = user_traffic_totals(session, user.id)
        raw_conns = list_subscription_connection_records(session, user.id)
        subs_dev_limit = effective_subscription_device_limit(cfg)
        subs_conns = [SubscriptionConnectionItem(**r) for r in raw_conns]
        return AccountMeResponse(
            role=role,
            id=user.id,
            email=user.email,
            telegram_id=user.telegram_id,
            telegram_properties=user.telegram_properties,
            telegram_bot_page_url=telegram_bot_public_page_url(cfg),
            registered_at=user.registered_at,
            subscription_until=user.subscription_until,
            subscription_active=user_has_active_subscription(user),
            subscription_token=user.token,
            subscription_open_clients=build_subscription_open_client_items(),
            subscription_connections_count=len(subs_conns),
            subscription_connections_limit=subs_dev_limit,
            subscription_connections=subs_conns,
            traffic_up_bytes=up_b,
            traffic_down_bytes=down_b,
            traffic_total_bytes=total_b,
            has_site_password=bool(user.password_hash),
        )

    if principal.role == "admin":
        if principal.user_id is None:
            raise HttpServiceError(401, "Недействительный токен")
        user = session.get(User, principal.user_id)
        if user is None:
            raise HttpServiceError(401, "Пользователь не найден")
        if user.account_role != "admin":
            raise HttpServiceError(401, "Недействительный токен")
        return response_for(user, role="admin")

    if principal.user_id is None:
        raise HttpServiceError(401, "Недействительный токен")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HttpServiceError(401, "Пользователь не найден")
    if not user.email and not user.telegram_id:
        raise HttpServiceError(500, "У записи нет ни email, ни telegram_id")

    api_role = "manager" if principal.role == "manager" else "user"
    return response_for(user, role=api_role)


def _account_user_for_password_change(session: Session, principal: BearerPrincipal) -> User:
    """Та же проверка субъекта, что у GET /api/auth/me (admin / manager / user)."""
    if principal.role == "admin":
        if principal.user_id is None:
            raise HttpServiceError(401, "Недействительный токен")
        user = session.get(User, principal.user_id)
        if user is None:
            raise HttpServiceError(401, "Пользователь не найден")
        if user.account_role != "admin":
            raise HttpServiceError(401, "Недействительный токен")
        return user
    if principal.user_id is None:
        raise HttpServiceError(401, "Недействительный токен")
    user = session.get(User, principal.user_id)
    if user is None:
        raise HttpServiceError(401, "Пользователь не найден")
    if not user.email and not user.telegram_id:
        raise HttpServiceError(500, "У записи нет ни email, ни telegram_id")
    return user


def change_account_password(
    session: Session,
    principal: BearerPrincipal,
    body: AccountChangePasswordBody,
) -> None:
    user = _account_user_for_password_change(session, principal)
    if not user.password_hash:
        raise HttpServiceError(
            400,
            "Для этого аккаунта не задан пароль входа на сайте. "
            "Задайте пароль при регистрации или через привязку email в боте.",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HttpServiceError(403, "Неверный текущий пароль")
    if len(body.new_password.encode("utf-8")) > 72:
        raise HttpServiceError(400, "Пароль слишком длинный (не более 72 байт в UTF-8)")
    if verify_password(body.new_password, user.password_hash):
        raise HttpServiceError(400, "Новый пароль совпадает с текущим")
    user.password_hash = hash_password(body.new_password)
    session.flush()
