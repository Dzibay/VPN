"""Сценарии входа и привязки Telegram: регистрация по telegram_id, привязка к сайту,
двусторонняя привязка из бота и обратно."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.auth_env import normalize_email
from app.core.dependencies import BearerPrincipal
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.passwords import hash_password, verify_password
from app.domain.auth.account_merge import merge_drop_user_into_keep
from app.domain.auth.jwt import issue_access_token_or_http_error, jwt_role_for_user
from app.domain.auth.permissions import user_can_add_credentials_from_site
from app.domain.auth.sync_tokens import (
    TelegramSyncRedisError,
    delete_site_cred_token,
    delete_telegram_link_token,
    generate_sync_token_value,
    get_telegram_link_user_id,
    resolve_site_cred_user_id,
    store_site_cred_token,
    store_telegram_link_token,
    sync_start_payload,
)
from app.domain.models.auth import (
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
    merge_telegram_auth_profile,
    telegram_auth_has_profile_fields,
)
from app.domain.public_urls import public_spa_base_url, telegram_bot_public_page_url
from app.domain.referrals.repository import increment_referral_counter
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.subscription.validity import (
    subscription_until_after_registration,
    user_has_active_subscription,
)
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.telegram_auth")


def telegram_authenticate(
    session: Session,
    body: TelegramAuthBody,
    cfg: Settings,
) -> TelegramAuthTokenResponse:
    """Аутентификация и регистрация по ``telegram_id`` (вызывается ботом).

    Если такого ``telegram_id`` ещё нет — создаём нового пользователя с триал-подпиской и
    учитываем реферальный токен (клик и регистрацию). Если есть — лишь обновляем профиль
    при наличии новых полей.
    """
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
                raise ConflictError(
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
    token = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
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
    """Привязка Telegram к сайтовому аккаунту по одноразовому токену из личного кабинета.

    Если в БД уже есть строка с тем же ``telegram_id``, пытаемся слить дубликат в основной
    аккаунт (только для ролей ``client``/``manager``).
    """
    key_part = body.link_token
    try:
        uid = get_telegram_link_user_id(redis_conn, key_part)
    except TelegramSyncRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None
    if uid is None:
        raise BadRequestError("Неверный или истёкший токен привязки")

    target = session.get(User, uid)
    if target is None:
        raise BadRequestError("Пользователь по токену не найден")
    if target.telegram_id is not None:
        raise ConflictError("Этот аккаунт уже привязан к Telegram")

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
            raise ForbiddenError(
                "Учётная запись с этим Telegram имеет недопустимую роль для объединения",
            )
        if target.account_role not in ("client", "manager"):
            raise ForbiddenError(
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
        delete_telegram_link_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram link: не удалось удалить одноразовый токен из Redis")

    return TelegramWebLinkResponse(status="merged" if merged else "linked", user_id=int(target.id))


def telegram_site_link_start(
    session: Session,
    body: TelegramSiteLinkStartBody,
    redis_conn: object,
    cfg: Settings,
) -> TelegramSiteLinkStartResponse:
    """Запуск сценария «Привязать аккаунт сайта» из бота.

    Если пользователю уже принадлежит сайтовый аккаунт с email и паролём, возвращаем готовую
    SSO-ссылку в кабинет (через JWT во фрагменте URL); иначе — одноразовую ссылку на форму
    ввода email и пароля.
    """
    stmt = select(User).where(User.telegram_id == body.telegram_id).limit(1)
    user = session.scalars(stmt).first()
    if user is None:
        raise NotFoundError(
            "Пользователь с таким Telegram не найден. Запустите бота и войдите в аккаунт.",
        )

    if user.account_role == "admin":
        raise ConflictError("Недопустимо для аккаунта администратора")

    mail = (getattr(user, "email", None) or "").strip()
    if mail and user.password_hash:
        base = public_spa_base_url(cfg)
        if not base:
            raise ServiceUnavailableError(
                "Не задан публичный URL SPA: задайте SITE_ADDRESS в окружении (полный URL или host[:port]).",
            )
        jwt_role = jwt_role_for_user(user)
        token = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
        site_url = f"{base}/cabinet#tg_sso_token={token}"
        return TelegramSiteLinkStartResponse(site_url=site_url, has_account=True)

    ok, reason = user_can_add_credentials_from_site(user)
    if not ok:
        raise ConflictError(reason or "Нельзя добавить данные сайта для этого аккаунта")

    base = public_spa_base_url(cfg)
    if not base:
        raise ServiceUnavailableError(
            "Не задан публичный URL SPA: задайте SITE_ADDRESS в окружении (полный URL или host[:port]).",
        )

    token_val = generate_sync_token_value()
    try:
        store_site_cred_token(redis_conn, token_val, int(user.id))
    except TelegramSyncRedisError:
        raise ServiceUnavailableError("Redis недоступен") from None

    site_url = f"{base}/link-from-telegram?token={quote(token_val, safe='')}"
    return TelegramSiteLinkStartResponse(site_url=site_url, has_account=False)


def telegram_site_link_preview_response(
    session: Session,
    redis_conn: object,
    raw_token: str,
    cfg: Settings,
) -> TelegramSiteLinkPreviewResponse:
    """Данные Telegram по одноразовому ``token`` из URL — нужны форме ещё до отправки."""
    uid, _ = resolve_site_cred_user_id(redis_conn, raw_token)
    user = session.get(User, uid)
    if user is None or user.telegram_id is None:
        raise NotFoundError("Пользователь не найден")

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
    """Завершение «Привязать аккаунт сайта»: создать новый email или объединить с существующим.

    Если email свободен — пишем его и ``password_hash`` в Telegram-аккаунт. Если email занят
    другим пользователем с сайтовым паролем — проверяем пароль и сливаем Telegram-аккаунт
    в найденный (победителем считается аккаунт с email).
    """
    uid, key_part = resolve_site_cred_user_id(redis_conn, body.link_token)

    tg_user = session.get(User, uid)
    if tg_user is None:
        raise NotFoundError("Пользователь не найден")

    ok, reason = user_can_add_credentials_from_site(tg_user)
    if not ok:
        raise ConflictError(reason or "Нельзя выполнить операцию")

    email_norm = normalize_email(str(body.email))
    stmt_existing = select(User).where(User.email == email_norm).limit(1)
    existing = session.scalars(stmt_existing).first()

    winner: User
    if existing is None:
        if len(body.password.encode("utf-8")) > 72:
            raise BadRequestError("Пароль слишком длинный для системы входа")
        if len(str(body.password)) < 8:
            raise BadRequestError("Пароль должен содержать не менее 8 символов")
        tg_user.email = email_norm
        tg_user.password_hash = hash_password(body.password)
        try:
            session.flush()
        except IntegrityError as e:
            session.rollback()
            log.warning("telegram site-link complete conflict: %s", e)
            raise ConflictError("Пользователь с таким email уже зарегистрирован") from e
        winner = tg_user
    else:
        if existing.id == tg_user.id:
            raise InternalServerError("Несогласованное состояние учётной записи")
        if not getattr(existing, "password_hash", None):
            raise ForbiddenError(
                "У аккаунта с этим email не задан пароль для входа на сайте. "
                "Восстановите доступ или напишите в поддержку.",
            )
        if not verify_password(body.password, existing.password_hash):
            raise UnauthorizedError("Неверный email или пароль")
        if existing.telegram_id is not None:
            raise ConflictError(
                "Аккаунт с этим email уже привязан к Telegram. Войдите на сайт с паролем.",
            )
        if existing.account_role not in ("client", "manager"):
            raise ForbiddenError("Учётная запись с этим email не поддерживает объединение")
        if tg_user.account_role not in ("client", "manager"):
            raise ForbiddenError("Telegram-аккаунт не поддерживает объединение")

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
            raise ConflictError(
                "Не удалось объединить учётные записи (конфликт данных). Попробуйте позже или обратитесь в поддержку.",
            ) from e
        winner = existing

    try:
        delete_site_cred_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram site-link: не удалось удалить токен из Redis")

    jwt_role = jwt_role_for_user(winner)
    jwt = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=winner.id)
    return TokenResponse(access_token=jwt, role=jwt_role)


def telegram_sync_start_link(
    session: Session,
    principal: BearerPrincipal,
    redis_conn: object,
    cfg: Settings,
) -> TelegramSyncStartResponse:
    """Одноразовая deep link-ссылка на бота для привязки Telegram (вызывается из кабинета)."""
    if principal.user_id is None:
        raise UnauthorizedError("Нужна авторизация под пользователем")
    user = session.get(User, principal.user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден")
    if user.telegram_id is not None:
        raise ConflictError("Telegram уже привязан к этому аккаунту")

    base = telegram_bot_public_page_url(cfg)
    if not base:
        raise ServiceUnavailableError("TELEGRAM_BOT_USERNAME не задан — ссылка на бота недоступна")

    token_val = generate_sync_token_value()
    try:
        store_telegram_link_token(redis_conn, token_val, int(user.id))
    except TelegramSyncRedisError:
        raise ServiceUnavailableError("Не удалось сохранить токен привязки (проверьте Redis)") from None

    payload = sync_start_payload(token_val)
    deep = f"{base}?start={quote(payload, safe='')}"
    return TelegramSyncStartResponse(telegram_deep_link=deep)
