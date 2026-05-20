from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants import BIGINT_MAX

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "user", "manager"] = Field(
        description="Роль в JWT: admin и manager соответствуют account_role в БД; user — клиентская запись (account_role=client).",
    )


class SubscriptionOpenClientItem(BaseModel):
    """Элемент списка клиентов для кнопок «Подключить» в личном кабинете."""

    client_code: str = Field(
        description="Идентификатор клиента в URL /sub/{subscription_token}/open/{client_code}"
    )
    display_name: str = Field(description="Подпись на кнопке")
    store_platforms: list[str] = Field(
        default_factory=list,
        description=(
            "Платформы, где заданы ссылки: windows, android, ios, macos, linux (сайт обязателен в данных; файл — опционально). "
            "Пустой список — показывать при любой выбранной платформе (только deeplink)."
        ),
    )


def build_subscription_open_client_items() -> list[SubscriptionOpenClientItem]:
    """Один список клиентов из app.domain.subscription.open_apps (как в GET /api/me)."""
    from app.domain.subscription.open_apps import list_subscription_open_apps, store_platform_tags

    return [
        SubscriptionOpenClientItem(
            client_code=a.client_code,
            display_name=a.display_name,
            store_platforms=store_platform_tags(a.store_links),
        )
        for a in list_subscription_open_apps()
    ]


class TelegramSubscriptionOpenClientsResponse(BaseModel):
    """Список клиентов и шаблон ссылок для бота; данные совпадают с subscription_open_clients в /api/me."""

    clients: list[SubscriptionOpenClientItem] = Field(
        description="Те же client_code/display_name/store_platforms, что отдаётся пользователю в ЛК.",
    )
    public_base_url: str | None = Field(
        default=None,
        description=(
            "Origin сайта из SITE_ADDRESS на бэкенде (HTTPS или http для локальной разработки, без «/» в конце). "
            "Ссылка на страницу открытия клиента (SPA): {public_base_url}/sub/{subscription_token}/open/{client_code} — "
            "если null, задайте SITE_ADDRESS в .env API."
        ),
    )
    open_path_template: str = Field(
        default="/sub/{subscription_token}/open/{client_code}",
        description="Относительный путь; опционально ?platform=windows|android|ios|macos|linux для «Скачать».",
    )


class AccountRegisterBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72, description="До 72 байт (ограничение bcrypt)")
    referral_token: str | None = Field(
        default=None,
        max_length=64,
        description="Реферальный токен из ?ref= на сайте (session/localStorage до регистрации)",
    )

    @field_validator("referral_token", mode="before")
    @classmethod
    def strip_referral_token(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v


class AccountLoginBody(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)


class TelegramAuthBody(BaseModel):
    """Вход/регистрация по Telegram: только вызов с доверенного бэкенда бота (секрет в заголовке)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "telegram_id": 123456789,
                    "username": "ivan_dev",
                    "first_name": "Иван",
                    "last_name": "Петров",
                    "topic_id": 2,
                    "referral_token": "abc123ref",
                }
            ]
        },
    )

    telegram_id: int = Field(
        ge=1,
        le=BIGINT_MAX,
        description="Числовой id пользователя в Telegram (как в Bot API).",
    )
    username: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Ник в Telegram (без @); сохраняется в users.telegram_properties.username."
        ),
    )
    first_name: str | None = Field(
        default=None,
        max_length=255,
        description="Имя; в users.telegram_properties.first_name.",
    )
    last_name: str | None = Field(
        default=None,
        max_length=255,
        description="Фамилия; в users.telegram_properties.last_name.",
    )
    topic_id: int | None = Field(
        default=None,
        ge=1,
        le=BIGINT_MAX,
        description="Id топика; в users.telegram_properties.topic_id.",
    )
    referral_token: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Реферальный токен (как ?ref= на сайте или deep link бота); "
            "учитывается только при первой регистрации пользователя по telegram_id."
        ),
    )

    @field_validator("referral_token", mode="before")
    @classmethod
    def strip_telegram_referral_token(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v


class TelegramKnownUserIdsResponse(BaseModel):
    """Ответ GET /api/telegram/users: все непустые telegram_id из таблицы users."""

    telegram_ids: list[int] = Field(
        description="Числовые id в Telegram по возрастанию (только строки с заполненным users.telegram_id).",
    )


def merge_telegram_auth_profile(
    body: "TelegramAuthBody",
    existing: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Собирает telegram_properties из полей запроса; пустые строки отбрасываются."""
    string_keys = ("username", "first_name", "last_name")
    out: dict[str, Any] = dict(existing) if existing else {}
    for key in string_keys:
        if key not in body.model_fields_set:
            continue
        val = getattr(body, key)
        if val is None:
            out.pop(key, None)
        else:
            s = str(val).strip()
            if s:
                out[key] = s
            else:
                out.pop(key, None)
    if "topic_id" in body.model_fields_set:
        tid = body.topic_id
        if tid is None:
            out.pop("topic_id", None)
        else:
            out["topic_id"] = int(tid)
    return out if out else None


def telegram_auth_has_profile_fields(body: "TelegramAuthBody") -> bool:
    return bool(
        {"username", "first_name", "last_name", "topic_id"} & set(body.model_fields_set),
    )


class TelegramSyncStartResponse(BaseModel):
    """Ответ POST /api/me/telegram-sync-start: ссылка с одноразовым токеном в ?start=."""

    telegram_deep_link: str = Field(
        description="Открыть в Telegram; параметр start вида link_<секрет> (до 64 символов, только A–Z, a–z, 0–9, _).",
    )


class TelegramWebLinkBody(BaseModel):
    """Привязка веб-аккаунта к Telegram по одноразовому токену (вызывает бэкенд бота)."""

    link_token: str = Field(
        ...,
        max_length=80,
        description="То, что пришло в /start после пробела: link_<token> или только <token>.",
    )
    telegram_id: int = Field(
        ge=1,
        le=BIGINT_MAX,
        description="Числовой id пользователя в Telegram (Bot API).",
    )
    username: str | None = Field(
        default=None,
        max_length=255,
        description="Ник без @ → users.telegram_properties.username",
    )
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    topic_id: int | None = Field(
        default=None,
        ge=1,
        le=BIGINT_MAX,
    )

    @field_validator("link_token", mode="before")
    @classmethod
    def strip_outer(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("link_token должен быть строкой")
        s = v.strip()
        if not s:
            raise ValueError("link_token не может быть пустым")
        return s

    @field_validator("link_token", mode="after")
    @classmethod
    def strip_link_prefix(cls, v: str) -> str:
        low = v.lower()
        if low.startswith("link_"):
            inner = v[5:].strip()
            if not inner:
                raise ValueError("Пустой токен после префикса link_")
            return inner
        return v


class TelegramWebLinkResponse(BaseModel):
    status: Literal["linked", "merged"] = Field(
        description="linked — только запись Telegram на целевой аккаунт; merged — удалён дубликат по telegram_id.",
    )
    user_id: int


class TelegramSiteLinkStartBody(BaseModel):
    """Запрос одноразовой ссылки на сайт (добавить email и пароль к учётке только-Telegram)."""

    telegram_id: int = Field(
        ge=1,
        le=BIGINT_MAX,
        description="Числовой id пользователя Telegram (Bot API); вызывает бэкенд бота.",
    )


class TelegramSiteLinkStartResponse(BaseModel):
    """Ответ боту: одна ссылка на сайт и признак, есть ли уже вход по email/паролю."""

    site_url: str = Field(
        description=(
            "При has_account=false — /link-from-telegram?token=… (форма email/пароль). "
            "При has_account=true — /cabinet#tg_sso_token=<JWT> (вход в кабинет)."
        ),
    )
    has_account: bool = Field(
        description="True, если у пользователя уже заданы email и пароль на сайте.",
    )


class TelegramSiteLinkPreviewResponse(BaseModel):
    telegram_id: int
    telegram_properties: dict[str, Any] | None = None
    subscription_until: date | None = None
    subscription_active: bool = Field(
        default=False,
        description="True, если срок подписки ещё действует (дата и лимит трафика).",
    )
    traffic_total_bytes: int = Field(
        default=0,
        ge=0,
        description="Накопленный трафик up+down по всем узлам, байты.",
    )
    traffic_limit_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Потолок трафика в байтах; null — без лимита.",
    )
    can_add_credentials: bool = Field(
        default=True,
        description="False — email уже задан, форма неактивна.",
    )


class TelegramSiteLinkCompleteBody(BaseModel):
    link_token: str = Field(
        ...,
        max_length=80,
        description="Тот же token, что в URL на сайте.",
    )
    email: EmailStr = Field(max_length=320)
    password: str = Field(
        min_length=1,
        max_length=72,
        description=(
            "Для первого сохранения email на Telegram-аккаунте — не короче 8 символов (проверка в endpoint). "
            "При объединении с уже существующим email — любой действующий пароль от этого аккаунта (до 72 байт bcrypt)."
        ),
    )

    @field_validator("link_token", mode="before")
    @classmethod
    def strip_link_token(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("link_token должен быть строкой")
        s = v.strip()
        if not s:
            raise ValueError("link_token не может быть пустым")
        return s


class SubscriptionConnectionItem(BaseModel):
    """Строка учёта устройства для личного кабинета (по запросам /sub/{token})."""

    id: int = Field(ge=1, description="Идентификатор строки subscription_devices.")
    os: str | None = Field(
        default=None,
        description="Заголовок x-device-os с последнего запроса конфигурации подписки.",
    )
    user_agent: str | None = Field(
        default=None,
        description="User-Agent клиента с последнего запроса подписки.",
    )


class AccountMeResponse(BaseModel):
    """Схема ответа GET /api/me; в Swagger смотрите примеры у этой операции."""

    role: str = Field(description="`user` | `admin` | `manager`")
    id: int | None = Field(
        default=None,
        description="Внутренний id в БД; у admin всегда null.",
    )
    email: str | None = Field(
        default=None,
        description="Email из БД; `null`, если регистрация только через Telegram.",
    )
    telegram_id: int | None = Field(
        default=None,
        description="Числовой id Telegram; `null`, если не привязан.",
    )
    telegram_properties: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Словарь из `username`, `first_name`, `last_name`, `topic_id` (и др.) "
            "из `/api/auth/telegram`; для `admin` — `null`."
        ),
    )
    telegram_bot_page_url: str | None = Field(
        default=None,
        description=(
            "Публичная ссылка на Telegram-бота (без deep-link); для кнопки в ЛК. "
            "Из TELEGRAM_BOT_USERNAME → https://t.me/{username}; `null`, если не задано."
        ),
    )
    registered_at: datetime | None = Field(
        default=None,
        description="Момент регистрации (UTC в БД); `null` у старых записей без даты.",
    )
    subscription_until: date | None = Field(
        default=None,
        description="Включительно; `null` — без срока или не задано.",
    )
    subscription_active: bool = Field(
        default=False,
        description="True, если срок подписки ещё действует.",
    )
    subscription_token: str = Field(
        default="",
        description=(
            "Токен для публичных URL `/sub/{token}` и `/sub/{token}/clash` "
            "(не JWT); у admin пустая строка."
        ),
    )
    subscription_open_clients: list[SubscriptionOpenClientItem] = Field(
        default_factory=list,
        description="Клиенты VPN для кнопок подключения в ЛК; у admin — пустой список.",
    )
    subscription_connections_count: int = Field(
        default=0,
        ge=0,
        description="Число зарегистрированных уникальных клиентов/устройств по запросам /sub/{token}.",
    )
    subscription_connections_limit: int | None = Field(
        default=None,
        description=(
            "Глобальный лимит уникальных устройств на пользователя для /sub/{token}; `null`, если ограничения нет "
            "(SUBSCRIPTION_MAX_DEVICES на API равен 0 или не задан)."
        ),
    )
    subscription_connections: list[SubscriptionConnectionItem] = Field(
        default_factory=list,
        description="Список зафиксированных подключений (os, user_agent), по убыванию updated_at.",
    )
    traffic_up_bytes: int = Field(
        default=0,
        ge=0,
        description=(
            "Сумма исходящего трафика по всем узлам, в байтах (не битах); "
            "те же единицы, что в Xray statsquery и user_server_traffic.up_bytes."
        ),
    )
    traffic_down_bytes: int = Field(
        default=0,
        ge=0,
        description="Сумма входящего трафика по всем узлам, в байтах (user_server_traffic.down_bytes).",
    )
    traffic_total_bytes: int = Field(
        default=0,
        ge=0,
        description="Итого в байтах: traffic_up_bytes + traffic_down_bytes.",
    )
    traffic_limit_bytes: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Персональный потолок трафика (байты, up+down); null — без лимита (обычно после оплаты)."
        ),
    )
    has_site_password: bool = Field(
        default=False,
        description="True, если задан пароль для входа на сайте (смена пароля в ЛК доступна).",
    )


class TelegramAuthUserResponse(AccountMeResponse):
    """Ответ POST /api/auth/telegram: те же поля, что GET /api/me, и признак первой регистрации."""

    is_new_user: bool = Field(
        description=(
            "True, если в этом запросе создана новая учётная запись по telegram_id "
            "(первая регистрация). False — пользователь уже существовал или повтор после гонки вставки."
        ),
    )


class AccountChangePasswordBody(BaseModel):
    """Смена пароля для текущего пользователя (JWT)."""

    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(
        min_length=8,
        max_length=72,
        description="Не короче 8 символов; до 72 байт в UTF-8 (ограничение bcrypt).",
    )
