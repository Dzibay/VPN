"""Сценарии входа и привязки Telegram: регистрация по telegram_id, привязка к сайту,
двусторонняя привязка из бота и обратно."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.request_subject import bind_request_subject_user
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
from app.domain.auth.credentials_validation import validate_new_site_password_with_confirm
from app.domain.auth.trusted_email_domains import validate_trusted_email_domain
from app.domain.auth.account_merge import merge_drop_user_into_keep
from app.domain.auth.jwt import issue_access_token_or_http_error, jwt_role_for_user
from app.domain.auth.permissions import user_can_add_credentials_from_site
from app.domain.auth.sync_tokens import (
    TelegramSyncRedisError,
    delete_site_cred_token,
    delete_telegram_link_token,
    generate_sync_token_value,
    get_or_issue_telegram_link_token,
    get_telegram_link_user_id,
    resolve_site_cred_user_id,
    store_site_cred_token,
    sync_start_payload,
)
from app.domain.models.auth import (
    RegisterAuthResponse,
    TelegramAuthBody,
    TelegramAuthUserResponse,
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
from app.domain.services.email_verification_service import (
    complete_email_registration_flow,
    mark_email_verified_now,
    user_has_verified_email,
)
from app.domain.services.auth_service import account_me_from_user
from app.domain.public_urls import public_spa_base_url, telegram_bot_public_page_url
from app.domain.referrals.registration_tasks import create_notify_ref_reg_task_if_applicable
from app.domain.referrals.repository import increment_referral_counter
from app.domain.tenant.project_context import ProjectContext, get_current_project
from app.domain.users.identifiers import new_subscription_token, new_vless_uuid
from app.domain.users.telegram_lookup import (
    require_project_context,
    user_by_telegram_id_in_project,
)
from app.domain.subscription.traffic_limit import apply_default_traffic_limit_for_new_client
from app.domain.subscription.validity import (
    subscription_until_after_registration,
    trial_extra_days_for_referral_link,
    user_has_active_subscription,
)
from app.domain.user_traffic import user_traffic_totals
from app.infrastructure.database.operations import table_insert
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.user import User

log = logging.getLogger("app.telegram_auth")


async def telegram_authenticate(
    session: AsyncSession,
    body: TelegramAuthBody,
    cfg: Settings,
    *,
    project: ProjectContext,
) -> TelegramAuthUserResponse:
    """Аутентификация и регистрация по ``telegram_id`` (вызывается ботом).

    Учётная запись изолирована по ``project.id`` (один telegram_id может быть в разных проектах).
    """
    tid = body.telegram_id
    project_id = int(project.id)
    profile = merge_telegram_auth_profile(body, None)
    user = await user_by_telegram_id_in_project(session, tid, project_id)
    is_new_user = False
    if user is None:
        rlink: ReferralLink | None = None
        if body.referral_token:
            rstmt = (
                select(ReferralLink)
                .where(
                    ReferralLink.token == body.referral_token,
                    ReferralLink.project_id == project_id,
                )
                .limit(1)
            )
            rlink = (await session.scalars(rstmt)).first()
        trial_extra = trial_extra_days_for_referral_link(rlink, cfg=cfg)
        user = User(
            project_id=project_id,
            email=None,
            password_hash=None,
            telegram_id=tid,
            telegram_properties=profile,
            account_role="client",
            subscription_until=subscription_until_after_registration(extra_trial_days=trial_extra, cfg=cfg),
            token=new_subscription_token(),
            vless_uuid=new_vless_uuid(),
        )
        apply_default_traffic_limit_for_new_client(user, cfg=cfg)
        try:
            await table_insert(session, user)
        except IntegrityError as e:
            log.warning("telegram register conflict, refetch: %s", e)
            await session.rollback()
            user = await user_by_telegram_id_in_project(session, tid, project_id)
            if user is None:
                other_project_user = (
                    await session.scalars(
                        select(User).where(User.telegram_id == tid).limit(1),
                    )
                ).first()
                if (
                    other_project_user is not None
                    and int(other_project_user.project_id) != project_id
                ):
                    raise ConflictError(
                        "Этот Telegram уже зарегистрирован в другом проекте VPN. "
                        "Нужна миграция БД (per-project telegram_id) или обращение в поддержку.",
                    ) from e
                raise ConflictError(
                    "Не удалось создать или найти пользователя по telegram_id",
                ) from e
        else:
            is_new_user = True
            if rlink is not None:
                user.referral_link_id = rlink.id
                await increment_referral_counter(session, rlink.id, "clicks")
                await increment_referral_counter(session, rlink.id, "registrations")
                await session.flush()
                await create_notify_ref_reg_task_if_applicable(
                    session,
                    referral_link=rlink,
                    referee_user_id=int(user.id),
                )
    elif telegram_auth_has_profile_fields(body):
        user.telegram_properties = merge_telegram_auth_profile(body, user.telegram_properties)
        await session.flush()

    bind_request_subject_user(int(user.id), source="telegram_bot_auth")
    me = await account_me_from_user(session, user, cfg, project=project)
    return TelegramAuthUserResponse(**me.model_dump(), is_new_user=is_new_user)


async def telegram_link_web_account(
    session: AsyncSession,
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

    project = require_project_context()
    project_id = int(project.id)
    target = await session.get(User, uid)
    if target is None:
        raise BadRequestError("Пользователь по токену не найден")
    if int(target.project_id) != project_id:
        raise BadRequestError("Токен привязки относится к другому проекту")
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

    stmt = select(User).where(
        User.telegram_id == tid,
        User.project_id == project_id,
    ).limit(1)
    other = (await session.scalars(stmt)).first()

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
        await merge_drop_user_into_keep(session, target, other)
        merged = True

    profile = merge_telegram_auth_profile(auth_fragment, telegram_props_base)

    target.telegram_id = tid
    target.telegram_properties = profile
    await session.flush()

    try:
        delete_telegram_link_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram link: не удалось удалить одноразовый токен из Redis")

    bind_request_subject_user(int(target.id), source="telegram_web_link")
    return TelegramWebLinkResponse(status="merged" if merged else "linked", user_id=int(target.id))


async def telegram_site_link_start(
    session: AsyncSession,
    body: TelegramSiteLinkStartBody,
    redis_conn: object,
    cfg: Settings,
) -> TelegramSiteLinkStartResponse:
    """Запуск сценария «Привязать аккаунт сайта» из бота.

    Если пользователю уже принадлежит сайтовый аккаунт с email и паролём, возвращаем готовую
    SSO-ссылку в кабинет (через JWT во фрагменте URL); иначе — одноразовую ссылку на форму
    ввода email и пароля.
    """
    project = require_project_context()
    stmt = select(User).where(
        User.telegram_id == body.telegram_id,
        User.project_id == int(project.id),
    ).limit(1)
    user = (await session.scalars(stmt)).first()
    if user is None:
        raise NotFoundError(
            "Пользователь с таким Telegram не найден. Запустите бота и войдите в аккаунт.",
        )

    if user.account_role == "admin":
        raise ConflictError("Недопустимо для аккаунта администратора")

    mail = (getattr(user, "email", None) or "").strip()
    if mail and user.password_hash:
        base = public_spa_base_url(cfg, project)
        if not base:
            raise ServiceUnavailableError(
                "Не задан публичный URL SPA: задайте SITE_ADDRESS в окружении (полный URL или host[:port]).",
            )
        if not user_has_verified_email(user):
            msg = (
                "Подтвердите email по ссылке из письма. "
                "Если письмо не пришло — запросите повторную отправку на этой странице."
            )
            q = f"email={quote(mail, safe='')}&message={quote(msg, safe='')}"
            site_url = f"{base}/verify-email-pending?{q}"
            bind_request_subject_user(int(user.id), source="telegram_site_link_start_unverified")
            return TelegramSiteLinkStartResponse(site_url=site_url, has_account=True)

        jwt_role = jwt_role_for_user(user)
        token = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=user.id)
        site_url = f"{base}/cabinet#tg_sso_token={token}"
        bind_request_subject_user(int(user.id), source="telegram_site_link_start_sso")
        return TelegramSiteLinkStartResponse(site_url=site_url, has_account=True)

    ok, reason = user_can_add_credentials_from_site(user)
    if not ok:
        raise ConflictError(reason or "Нельзя добавить данные сайта для этого аккаунта")

    base = public_spa_base_url(cfg, project)
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
    bind_request_subject_user(int(user.id), source="telegram_site_link_start_form")
    return TelegramSiteLinkStartResponse(site_url=site_url, has_account=False)


async def telegram_site_link_preview_response(
    session: AsyncSession,
    redis_conn: object,
    raw_token: str,
    cfg: Settings,
) -> TelegramSiteLinkPreviewResponse:
    """Данные Telegram по одноразовому ``token`` из URL — нужны форме ещё до отправки."""
    uid, _ = resolve_site_cred_user_id(redis_conn, raw_token)
    user = await session.get(User, uid)
    if user is None or user.telegram_id is None:
        raise NotFoundError("Пользователь не найден")
    project = get_current_project()
    if project is not None and int(user.project_id) != int(project.id):
        raise NotFoundError("Пользователь не найден")

    ok, _ = user_can_add_credentials_from_site(user)
    bind_request_subject_user(int(user.id), source="telegram_site_link_preview")
    _, _, total_b = await user_traffic_totals(session, int(user.id))
    return TelegramSiteLinkPreviewResponse(
        telegram_id=int(user.telegram_id),
        telegram_properties=user.telegram_properties,
        subscription_until=user.subscription_until,
        subscription_active=user_has_active_subscription(user, used_bytes=total_b),
        traffic_total_bytes=int(total_b),
        traffic_limit_bytes=(
            int(user.traffic_limit_bytes) if user.traffic_limit_bytes is not None else None
        ),
        can_add_credentials=ok,
    )


async def telegram_site_link_complete(
    session: AsyncSession,
    body: TelegramSiteLinkCompleteBody,
    redis_conn: object,
    cfg: Settings,
) -> RegisterAuthResponse:
    """Завершение «Привязать аккаунт сайта»: создать новый email или объединить с существующим.

    Если email свободен — пишем его и ``password_hash`` в Telegram-аккаунт. Если email занят
    другим пользователем с сайтовым паролем — проверяем пароль и сливаем Telegram-аккаунт
    в найденный (победителем считается аккаунт с email).
    """
    uid, key_part = resolve_site_cred_user_id(redis_conn, body.link_token)

    tg_user = await session.get(User, uid)
    if tg_user is None:
        raise NotFoundError("Пользователь не найден")
    project = get_current_project()
    if project is not None and int(tg_user.project_id) != int(project.id):
        raise NotFoundError("Пользователь не найден")

    ok, reason = user_can_add_credentials_from_site(tg_user)
    if not ok:
        raise ConflictError(reason or "Нельзя выполнить операцию")

    email_norm = normalize_email(str(body.email))
    stmt_existing = select(User).where(User.email == email_norm).limit(1)
    if project is not None:
        stmt_existing = stmt_existing.where(User.project_id == int(project.id))
    existing = (await session.scalars(stmt_existing)).first()

    winner: User
    new_email_on_tg_account = False
    if existing is None:
        validate_trusted_email_domain(email_norm)
        validate_new_site_password_with_confirm(body.password, body.password_confirm)
        tg_user.email = email_norm
        tg_user.password_hash = await run_in_threadpool(hash_password, body.password)
        try:
            await session.flush()
        except IntegrityError as e:
            await session.rollback()
            log.warning("telegram site-link complete conflict: %s", e)
            raise ConflictError("Пользователь с таким email уже зарегистрирован") from e
        winner = tg_user
        new_email_on_tg_account = True
    else:
        if existing.id == tg_user.id:
            raise InternalServerError("Несогласованное состояние учётной записи")
        if not getattr(existing, "password_hash", None):
            raise ForbiddenError(
                "У аккаунта с этим email не задан пароль для входа на сайте. "
                "Восстановите доступ или напишите в поддержку.",
            )
        pw_ok = await run_in_threadpool(verify_password, body.password, existing.password_hash)
        if not pw_ok:
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
            await merge_drop_user_into_keep(session, existing, tg_user)
            existing.telegram_id = tid
            existing.telegram_properties = tprops
            await session.flush()
        except IntegrityError as e:
            await session.rollback()
            log.warning("telegram site-link merge integrity: %s", e)
            raise ConflictError(
                "Не удалось объединить учётные записи (конфликт данных). Попробуйте позже или обратитесь в поддержку.",
            ) from e
        if not user_has_verified_email(existing):
            await mark_email_verified_now(session, existing)
        winner = existing

    try:
        delete_site_cred_token(redis_conn, key_part)
    except TelegramSyncRedisError:
        log.warning("telegram site-link: не удалось удалить токен из Redis")

    if new_email_on_tg_account:
        result = await complete_email_registration_flow(
            session,
            winner,
            cfg,
            redis_conn,
            bind_source="telegram_site_link_complete",
        )
        if isinstance(result, TokenResponse):
            return RegisterAuthResponse.from_token(result)
        return RegisterAuthResponse.from_pending(result)

    jwt_role = jwt_role_for_user(winner)
    jwt = issue_access_token_or_http_error(cfg, role=jwt_role, user_id=winner.id)
    bind_request_subject_user(int(winner.id), source="telegram_site_link_complete")
    return RegisterAuthResponse.from_token(TokenResponse(access_token=jwt, role=jwt_role))


async def telegram_sync_start_link(
    session: AsyncSession,
    principal: BearerPrincipal,
    redis_conn: object,
    cfg: Settings,
) -> TelegramSyncStartResponse:
    """Одноразовая deep link-ссылка на бота для привязки Telegram (вызывается из кабинета)."""
    if principal.user_id is None:
        raise UnauthorizedError("Нужна авторизация под пользователем")
    user = await session.get(User, principal.user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден")
    if user.telegram_id is not None:
        raise ConflictError("Telegram уже привязан к этому аккаунту")

    base = telegram_bot_public_page_url(cfg)
    if not base:
        raise ServiceUnavailableError("TELEGRAM_BOT_USERNAME не задан — ссылка на бота недоступна")

    try:
        token_val = get_or_issue_telegram_link_token(redis_conn, int(user.id))
    except TelegramSyncRedisError:
        raise ServiceUnavailableError("Не удалось сохранить токен привязки (проверьте Redis)") from None

    payload = sync_start_payload(token_val)
    deep = f"{base}?start={quote(payload, safe='')}"
    bind_request_subject_user(int(user.id), source="telegram_sync_start")
    return TelegramSyncStartResponse(telegram_deep_link=deep)
