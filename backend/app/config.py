import json
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import constants


class Settings(BaseSettings):
    """
    Подключение к PostgreSQL:

    - Если задан непустой ``DATABASE_URL`` — используется он (логин и пароль внутри ссылки).
    - Иначе строка собирается из ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASSWORD``, ``DB_NAME``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VPN API"
    api_version: str = Field(default="1.0.0", description="Версия API в OpenAPI / Swagger")
    debug: bool = False
    log_level: str = "INFO"

    http_audit_db_log_level: str = Field(
        default="OFF",
        description=(
            "Логи в БД (user_http_request_traces), по смыслу как уровни логирования консоли. "
            "OFF — отключено; INFO — только запросы, где уже известен user_id (JWT или /sub/…); "
            "DEBUG — все запросы, в том числе без пользователя (аналог «подробного» режима). "
            "Строки WARNING/ERROR/CRITICAL трактуются как INFO. Env: HTTP_AUDIT_DB_LOG_LEVEL."
        ),
    )
    api_prefix: str = "/api"

    database_url: str | None = Field(
        default=None,
        description="Полный DSN (postgresql://… или postgresql+psycopg://…). Пусто — брать DB_* .",
    )

    db_host: str = Field(default="127.0.0.1", description="Хост PostgreSQL")
    db_port: int = Field(default=5432, description="Порт PostgreSQL")
    db_user: str = Field(default="vpn", description="Имя пользователя БД")
    db_password: str = Field(default="vpn", description="Пароль БД")
    db_name: str = Field(default="vpn", description="Имя базы данных")

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cors_origin_regex: str = Field(
        default="",
        description=(
            "Regex для дополнительных Origin (Starlette CORSMiddleware). "
            "Пусто — только cors_origins. Для одного HTTPS-домена: https://vpn\\.example\\.com"
        ),
    )

    jwt_secret: str = Field(
        default="",
        description=(
            "Секрет HS256 для JWT (портал и админ-API). "
            "В режиме DEBUG=true пусто допустимо (используется небезопасный локальный ключ); "
            "при DEBUG=false старт API падает (см. core/startup_checks.py): без секрета "
            "защита require_roles отключается и админ-API становится открытым. "
            "Сгенерировать сильный ключ: `openssl rand -hex 32`."
        ),
    )
    staff_super_admins: str = Field(
        default="",
        description=(
            "Список super_admin аккаунтов (bootstrap). Формат: "
            "``email1|password1,email2|password2`` (запятая между записями, | между email и паролем). "
            "На каждом старте API проверяется: аккаунт с ролью super_admin и таким email или "
            "создаётся, или обновляется (пароль перезаписывается, роль повышается до super_admin). "
            "Пусто — ничего не делает. Обратная совместимость: если задан только один "
            "STAFF_ADMIN_EMAIL+STAFF_ADMIN_PASSWORD (legacy), используется как одна запись."
        ),
    )
    staff_managers: str = Field(
        default="",
        description=(
            "Список admin/manager аккаунтов (bootstrap). Формат: "
            "``email|password|role|project_slugs``, записи через запятую. "
            "role: admin | manager. project_slugs: список slug'ов через ``;`` (``*`` = все). "
            "Пример: ``pm@acme.com|secret|admin|podorozhnik;halyal,ops@acme.com|s|manager|*``. "
            "На каждом старте: аккаунт создаётся/обновляется (email, пароль, роль, проекты синхронизируются). "
            "Записи из env — источник истины: удаление из env НЕ удаляет staff, но их можно "
            "удалить через админку. Проекты доступа удаляются, если их нет в env."
        ),
    )
    staff_admin_email: str = Field(
        default="",
        description=(
            "Legacy-поле: bootstrap-логин одного super_admin. Оставлено для обратной совместимости. "
            "Рекомендуется использовать STAFF_SUPER_ADMINS (поддерживает несколько записей)."
        ),
    )
    staff_admin_password: str = Field(
        default="",
        description="Legacy-пароль к STAFF_ADMIN_EMAIL. См. STAFF_SUPER_ADMINS.",
    )
    admin_site_address: str = Field(
        default="",
        description=(
            "Отдельный домен админки (ADMIN_SITE_ADDRESS в env), напр. admin.example.com. "
            "Используется в CORS и как источник Origin, куда admin-UI шлёт X-Admin-Project. "
            "Не является tenant-доменом — на нём живёт только staff-панель."
        ),
    )
    bootstrap_projects: str = Field(
        default="",
        description=(
            "Bootstrap списка проектов при старте API. Формат: ``slug|name|primary_domain|extra_domains``, "
            "записи через запятую, extra_domains через ``;``. Пример: "
            "``podorozhnik|Подорожник VPN|podorozhnik-connect.ru|,halyal|Halyal VPN|halyal-connect.ru|``. "
            "Если проект по slug уже есть — обновляются только name/primary_domain/extra_domains, "
            "остальные поля (ключи, брендинг) не трогаются. Пусто — bootstrap выключен."
        ),
    )
    telegram_bot_api_secret: str = Field(
        default="",
        description=(
            "Секрет для POST /api/auth/telegram, POST /api/telegram/link, POST /api/telegram/site-link/start, "
            "GET /api/telegram/referral/me, DELETE /api/telegram/subscription-devices/{device_id}, "
            "GET /api/telegram/payments/tariffs, GET /api/telegram/payments/tribute-links, "
            "POST /api/telegram/payments/yookassa/checkout, "
            "POST /api/payments/tribute/webhook-test, "
            "POST /api/payments/yookassa/webhook, "
            "GET /api/telegram/notification-tasks, POST /api/telegram/notification-tasks/completed, "
            "GET /api/telegram/users?group=..., GET /api/telegram/users/{topic_id} и "
            "GET /api/telegram/subscription-open-clients: "
            "заголовок X-Telegram-Bot-Secret (вызывает только бэкенд бота, не Telegram-клиент). "
            "Пусто — эндпоинты отвечают 503."
        ),
    )
    site_address: str = Field(
        default="",
        description=(
            "Основной публичный URL сайта (env SITE_ADDRESS): полный URL или host[:port] без схемы. "
            "Канонический origin для рефералов, ссылок бота и редиректов /sub/…; "
            "дополнительные домены — в SITE_EXTRA_ADDRESSES."
        ),
    )
    site_extra_addresses: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Дополнительные домены (env SITE_EXTRA_ADDRESSES), через запятую: cool-vpn.ru, alt.example.com. "
            "Тот же сайт и TLS, что у SITE_ADDRESS; канонические ссылки остаются на основном домене."
        ),
    )
    public_cabinet_url: str = Field(
        default="",
        description=(
            "Куда вести при неверном /sub/{token}/open/{client}: личный кабинет. "
            "Пусто — относительный путь /cabinet на том же хосте. "
            "Иначе полный URL (https://vpn.example.com/cabinet) или путь (/cabinet)."
        ),
    )
    telegram_bot_username: str = Field(
        default="",
        description=(
            "Username Telegram-бота без @ (env: TELEGRAM_BOT_USERNAME). "
            "Ссылки: https://t.me/{username}, рефералы — …?start={token}, страница бота в ЛК."
        ),
    )
    support_telegram_username: str = Field(
        default="",
        description=(
            "Аккаунт поддержки в Telegram без @ (env: SUPPORT_TELEGRAM_USERNAME). "
            "Ссылка https://t.me/{username} — в ЛК после оплаты, заголовок support-url подписки."
        ),
    )

    smtp_host: str = Field(
        default="",
        description="SMTP-хост для писем подтверждения email. Пусто — в DEBUG авто-подтверждение.",
    )
    smtp_port: int = Field(default=587, ge=1, le=65535, description="Порт SMTP (обычно 587 или 465).")
    smtp_user: str = Field(default="", description="Логин SMTP (пусто — без AUTH).")
    smtp_password: str = Field(default="", description="Пароль SMTP.")
    smtp_from_email: str = Field(
        default="",
        description="Адрес отправителя (From). Пусто — smtp_user или noreply@localhost.",
    )
    smtp_from_name: str = Field(
        default="",
        description="Имя отправителя в письме. Пусто — app_name.",
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="STARTTLS на smtp_port (false — plain или SSL на 465, см. smtp_use_ssl).",
    )
    smtp_use_ssl: bool = Field(
        default=False,
        description="SMTP_SSL (порт 465): соединение сразу по TLS.",
    )
    email_verification_ttl_sec: int = Field(
        default=86400,
        ge=300,
        le=604800,
        description="Срок жизни ссылки подтверждения email в Redis (секунды).",
    )
    email_verification_resend_cooldown_sec: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Минимальный интервал между повторными письмами подтверждения (секунды).",
    )

    referral_bonus_days_per_paid_month: int = Field(
        default=3,
        ge=0,
        le=365,
        description=(
            "Сколько бонусных дней подписки получает реферер за каждый оплаченный реферируемым месяц. "
            "При оплате реферируемым ``months`` месяцев реферер получает ``months × значение`` дней. "
            "0 — бонус отключён: задача ``notify_ref_pay`` не создаётся, продление рефереру не выполняется. "
            "Счётчик ``referral_links.payments_count`` инкрементится в любом случае при оплате реферируемым."
        ),
    )
    referral_fixed_first_payment_bonus_rub: int = Field(
        default=500,
        ge=1,
        le=1_000_000,
        description=(
            "Фиксированная сумма (руб.) на баланс реферера при первой оплате каждого приведённого друга "
            "(политика ``fixed_first_payment_balance``). Переопределяется полем "
            "``users.referral_fixed_bonus_kopecks``."
        ),
    )
    referral_links_api_key: str = Field(
        default="",
        description=(
            "Секрет для POST /api/referral/external/links (автогенерация реферальных ссылок внешними сервисами): "
            "заголовок X-API-Key. Пусто — эндпоинт отвечает 503. Env: REFERRAL_LINKS_API_KEY."
        ),
    )

    tribute_api_key: str = Field(
        default="",
        description=(
            "Api-Key Tribute (Creator Dashboard → Settings → API Keys). Используется ТОЛЬКО как "
            "секрет для проверки подписи webhook (заголовок trbt-signature, HMAC-SHA256 от raw body). "
            "Пусто — POST /api/payments/tribute/webhook отвечает 503 (эндпоинт отключён)."
        ),
    )
    yookassa_shop_id: str = Field(
        default="",
        description="Идентификатор магазина ЮKassa (shopId). Пусто — оплата на сайте отключена.",
    )
    yookassa_secret_key: str = Field(
        default="",
        description="Секретный ключ ЮKassa. Пусто — оплата на сайте отключена.",
    )
    yookassa_return_url: str = Field(
        default="",
        description=(
            "URL возврата после оплаты с сайта (redirect). Пусто — {SITE_ADDRESS}/cabinet/pay/return. "
            "Оплата из бота всегда возвращает на {SITE_ADDRESS}/cabinet/pay/return/bot."
        ),
    )
    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Redis для очереди установки ПО на узлы (RQ).",
    )
    redis_install_queue_name: str = Field(
        default="server_install",
        description="Имя очереди RQ для задач провижининга.",
    )
    provision_job_timeout: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Таймаут одной задачи RQ (секунды).",
    )
    provision_command: str = Field(
        default="",
        description=(
            "Если не пусто — выполняется эта shell-команда на машине воркера вместо SSH-установки xray. "
            "Env: SERVER_HOST, SERVER_PORT, SERVER_ID."
        ),
    )
    provision_subprocess_timeout: int = Field(
        default=1800,
        ge=10,
        le=86400,
        description="Таймаут SSH / provision_command (секунды).",
    )
    provision_ssh_port: int = Field(
        default=22,
        ge=1,
        le=65535,
        description="Порт SSH на узле.",
    )
    provision_ssh_key_path: str = Field(
        default="",
        description="Путь к приватному ключу SSH на машине воркера; пусто — ssh по умолчанию (~/.ssh/config, agent).",
    )
    provision_ssh_extra_args: str = Field(
        default="",
        description="Доп. аргументы ssh (через пробел), напр. -J jump@host.",
    )
    provision_xray_installer_url: str = Field(
        default="https://github.com/XTLS/Xray-install/raw/main/install-release.sh",
        description=(
            "URL install-release.sh на удалённом хосте (curl/wget). Скрипт XTLS дополнительно качает бинарник с GitHub — "
            "нужен исходящий HTTPS до github.com (при SSL timeout на ВМ используйте прокси или ручную установку xray)."
        ),
    )
    provision_certbot_email: str = Field(
        default="",
        description=(
            "Email для Let's Encrypt (certbot) при VLESS gRPC+TLS; "
            "пусто — admin@{домен узла} на удалённом хосте."
        ),
    )
    provision_install_node_exporter: bool = Field(
        default=True,
        description="При провижининге ставить node_exporter (systemd) для Prometheus.",
    )
    provision_node_exporter_version: str = Field(
        default="1.8.2",
        description="Версия node_exporter (релиз GitHub prometheus/node_exporter).",
    )
    provision_node_exporter_port: int = Field(
        default=9100,
        ge=1,
        le=65535,
        description="Порт HTTP node_exporter (--web.listen-address).",
    )
    provision_node_exporter_listen_host: str = Field(
        default="0.0.0.0",
        description="Адрес прослушивания node_exporter (0.0.0.0 — для scrape снаружи).",
    )

    cascade_ru_split_routing: bool = Field(
        default=True,
        description=(
            "Каскадный РФ-вход: geosite:category-ru + *.ru/.su/.рф (regexp), geosite:private, geoip:ru → direct; остальное на exit. "
            "False — весь трафик через exit, как раньше."
        ),
    )
    xray_remote_api_port: int = Field(
        default=10085,
        ge=1,
        le=65535,
        description="Порт Stats API Xray на 127.0.0.1 узла (совпадает с inbound в config.json).",
    )
    xray_remote_binary_path: str = Field(
        default="/usr/local/bin/xray",
        description="Путь к бинарнику xray на удалённом узле (команда api statsquery).",
    )
    xray_vless_inbound_tag: str = Field(
        default="vpn-vless-in",
        description=(
            "Тег основного VLESS inbound в config.json на узле; используется ``xray api inbounduser/adu/rmu``. "
            "Должен совпадать с тем, что пишет провижининг (VPN_VLESS_INBOUND_TAG)."
        ),
    )
    xray_dynamic_client_sync_enabled: bool = Field(
        default=True,
        description=(
            "Сначала выравнивать список клиентов через ``xray api`` (inbounduser → rmu/adu) без рестарта; "
            "при ошибке в лог пишется причина и выполняется полный sync_clients (как раньше)."
        ),
    )
    xray_api_operation_timeout_seconds: int = Field(
        default=120,
        ge=5,
        le=900,
        description="Таймаут (-timeout) одного вызова ``xray api`` на узле (inbounduser, adu, rmu).",
    )
    xray_sync_all_servers_parallelism: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Параллельных узлов в одной RQ-задаче sync_xray_clients_all_servers (разные server_id).",
    )
    xray_stats_ssh_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=600.0,
        description=(
            "Таймаут SSH для xray api statsquery (отдельно от provision_subprocess_timeout). "
            "Должен быть ≥ proxy_read_timeout nginx и согласован с фронтом (~120 с)."
        ),
    )
    xray_traffic_collect_schedule_enabled: bool = Field(
        default=True,
        description=(
            "Фоновый планировщик API: периодически ставит в RQ батч-сбор трафика Xray "
            "(SSH statsquery) по всем активным provision_ready узлам."
        ),
    )
    xray_traffic_collect_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=86400,
        description="Интервал между попытками поставить батч-сбор в очередь (секунды).",
    )
    xray_traffic_collect_initial_delay_seconds: int = Field(
        default=45,
        ge=0,
        le=3600,
        description="Задержка перед первым тиком планировщика после старта API.",
    )
    xray_traffic_collect_stagger_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
        description="Пауза между опросом узлов внутри одной батч-задачи RQ (снижает пики SSH).",
    )
    stats_users_daily_auto_refresh: bool = Field(
        default=False,
        description=(
            "Устарело: после батч-сбора трафика делать полный fn_refresh_stats_users_daily_msk. "
            "По умолчанию выключено — умный кэш помечает холодные дни dirty и flush в scheduler."
        ),
    )
    stats_users_daily_flush_schedule_enabled: bool = Field(
        default=True,
        description="Периодически вызывать fn_stats_users_daily_flush_dirty в scheduler-periodic.",
    )
    stats_users_daily_flush_interval_seconds: int = Field(
        default=90,
        ge=15,
        le=3600,
        description="Интервал flush очереди stats_users_daily_dirty (сек).",
    )
    stats_users_daily_flush_initial_delay_seconds: int = Field(
        default=50,
        ge=0,
        le=600,
        description="Задержка перед первым flush очереди stats_users_daily_dirty после старта scheduler.",
    )
    stats_users_daily_traffic_dirty_days: int = Field(
        default=31,
        ge=7,
        le=365,
        description="После батч-сбора трафика: пометить столько холодных дней для пересчёта.",
    )
    stats_users_daily_query_timeout_seconds: int = Field(
        default=45,
        ge=5,
        le=300,
        description="statement_timeout для запросов графиков пользователей (сек).",
    )
    stats_users_daily_lock_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="lock_timeout для запросов графиков (сек) — не ждать flush/refresh.",
    )
    xray_traffic_batch_job_timeout_seconds: int = Field(
        default=7200,
        ge=300,
        le=86400,
        description="Таймаут RQ для батч-задачи сбора трафика по всем серверам.",
    )
    trial_traffic_limit_enabled: bool = Field(
        default=True,
        description=(
            "После батч-сбора трафика Xray: сравнивать накопленный трафик с users.traffic_limit_bytes, "
            "при превышении ставить sync клиентов на узлах (снятие UUID с конфигов), "
            "создавать задачи notify_traffic_low (<1 GiB остатка) и notify_traffic_over."
        ),
    )
    trial_traffic_limit_gib: int = Field(
        default=constants.TRIAL_TRAFFIC_LIMIT_GIB,
        ge=1,
        le=10_000,
        description="Лимит накопленного трафика (GiB, up+down) для пользователей без оплат.",
    )
    subscription_daily_xray_clients_sync_enabled: bool = Field(
        default=True,
        description=(
            "Планировщик API: раз в сутки (Europe/Moscow) ставить в очередь RQ "
            "синхронизацию клиентов Xray на всех узлах: перебор узлов через тот же путь, что и при регистрации "
            "(динамический diff без рестарта при возможности и полная перезапись config для согласованности)."
        ),
    )
    subscription_daily_xray_clients_sync_hour_local: int = Field(
        default=0,
        ge=0,
        le=23,
        description="Час Europe/Moscow для ежедневного sync Xray (после полуночи МСК — снятие истёкших клиентов).",
    )
    subscription_daily_xray_clients_sync_minute_local: int = Field(
        default=5,
        ge=0,
        le=59,
        description="Минута Europe/Moscow для ежедневного sync Xray.",
    )
    scheduler_role: Literal["all", "periodic", "telegram_notify"] = Field(
        default="all",
        description=(
            "Какие циклы поднимает ``python -m app.scheduler.run``: "
            "all — все; periodic — Xray-трафик, ежедневный sync Xray, Prometheus load, TCP-доступность; "
            "telegram_notify — задачи в таблице tasks (окончание подписки, post-reg ~1 ч). "
            "Env: SCHEDULER_ROLE."
        ),
    )
    subscription_expiry_notify_schedule_enabled: bool = Field(
        default=True,
        description=(
            "Раз в сутки (Europe/Moscow, по умолчанию 12:00) создавать ``notify_sub_expire_3d`` / "
            "``notify_sub_expire_1d`` / ``notify_sub_expire_0d`` / ``notify_sub_expired_7d``. "
            "``notify_sub_expire`` создаётся в полночь вместе с ежедневным sync Xray."
        ),
    )
    subscription_expiry_notify_hour_local: int = Field(
        default=12,
        ge=0,
        le=23,
        description="Час Europe/Moscow ежедневной проверки срока подписки (по умолчанию 12:00 МСК).",
    )
    subscription_expiry_notify_minute_local: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Минута Europe/Moscow проверки срока подписки.",
    )
    post_registration_notify_schedule_enabled: bool = Field(
        default=True,
        description=(
            "Периодически создавать ``notify_reg_1h_has_traffic`` / ``notify_reg_1h_no_traffic`` "
            "для пользователей с telegram_id примерно через час после ``registered_at``."
        ),
    )
    post_registration_notify_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Интервал опроса (сек) для post-reg задач в scheduler-telegram-notify.",
    )
    post_registration_notify_initial_delay_seconds: int = Field(
        default=30,
        ge=0,
        le=3600,
        description="Задержка перед первым тиком post-reg планировщика.",
    )
    post_registration_notify_delay_hours: float = Field(
        default=1.0,
        ge=0.1,
        le=168.0,
        description="Минимум часов после ``registered_at`` перед созданием задачи.",
    )
    post_registration_notify_lookback_minutes: int = Field(
        default=30,
        ge=5,
        le=10_080,
        description=(
            "Окно «свежих» регистраций: обрабатываются только пользователи с "
            "``registered_at`` не раньше delay + lookback (защита от бэклога при деплое). "
            "Увеличьте при длительном простое scheduler."
        ),
    )
    post_registration_notify_include_backlog: bool = Field(
        default=False,
        description=(
            "Если true — без ограничения lookback: все пользователи старше delay без post-reg задачи. "
            "Осторожно при первом включении на проде."
        ),
    )
    subscription_max_devices: int = Field(
        default=0,
        ge=0,
        le=10_000,
        description=(
            "Максимум разных устройств (по x-hwid или по отпечатку заголовков), с которых можно "
            "запрашивать подписку /sub/{token} (в т. ч. YAML при User-Agent с clash/hiddify или путь /sub/{token}/clash). 0 — без ограничения. "
            "Переменная окружения: SUBSCRIPTION_MAX_DEVICES."
        ),
    )
    happ_provider_id: str = Field(
        default="",
        description=(
            "Provider ID с happ-proxy.com для расширенных параметров подписки Happ "
            "(hide-settings, subscription-ping-onopen-enabled и т.д.). Пусто — не отдавать providerid. "
            "Переменная окружения: HAPP_PROVIDER_ID."
        ),
    )
    subscription_sub_expire_enabled: bool = Field(
        default=True,
        description=(
            "``sub-expire: 1`` в ответах /sub/… (баннер Happ за 3 дня до окончания и после). "
            "``false`` — ``sub-expire: 0``. Env: SUBSCRIPTION_SUB_EXPIRE_ENABLED."
        ),
    )
    subscription_sub_expire_button_link: str = Field(
        default="",
        description=(
            "``sub-expire-button-link``. Пусто — ``https://t.me/{TELEGRAM_BOT_USERNAME}``. "
            "Env: SUBSCRIPTION_SUB_EXPIRE_BUTTON_LINK."
        ),
    )
    subscription_sub_info_text: str = Field(
        default="",
        description=(
            "Текст информационного баннера ``sub-info-text`` (до 200 символов). Пусто — не показывать. "
            "Скрывается, если активен expire-баннер. Env: SUBSCRIPTION_SUB_INFO_TEXT."
        ),
    )
    subscription_sub_info_color: str = Field(
        default="blue",
        description="Цвет ``sub-info-color``: red | blue | green. Env: SUBSCRIPTION_SUB_INFO_COLOR.",
    )
    subscription_sub_info_button_text: str = Field(
        default="",
        description="Текст кнопки ``sub-info-button-text`` (до 25 символов). Env: SUBSCRIPTION_SUB_INFO_BUTTON_TEXT.",
    )
    subscription_sub_info_button_link: str = Field(
        default="",
        description="Ссылка кнопки ``sub-info-button-link``. Env: SUBSCRIPTION_SUB_INFO_BUTTON_LINK.",
    )

    prometheus_base_url: str = Field(
        default="",
        description="Базовый URL Prometheus API, напр. http://127.0.0.1:9090 — для аналитики node_exporter.",
    )
    prometheus_timeout_seconds: float = Field(
        default=20.0,
        ge=2.0,
        le=120.0,
        description="Таймаут HTTP к Prometheus при query_range.",
    )
    prometheus_range_retries: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Число попыток query_range при 502/503 (1 — без повторов, меньше «залипаний»).",
    )
    prometheus_circuit_cooldown_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=600.0,
        description="Пауза без запросов к Prometheus после серии ошибок (circuit breaker).",
    )
    prometheus_trust_env: bool = Field(
        default=False,
        description=(
            "Передавать в httpx trust_env: True — учитывать HTTP_PROXY. "
            "False (по умолчанию) — запросы к Prometheus без системного прокси (удобно для 127.0.0.1:9090)."
        ),
    )
    prometheus_online_clients_query: str = Field(
        default="",
        description=(
            "Опционально: PromQL для instant query — число онлайн VPN-клиентов на узле. "
            "В строке используйте плейсхолдер {instance} (подставится label instance как в node_exporter). "
            "Пусто — в аналитике показывается только TCP established из node_exporter."
        ),
    )
    prometheus_sd_token: str = Field(
        default="",
        description=(
            "Секрет Bearer для GET /api/prometheus/sd/node-exporter (HTTP SD). "
            "Пусто — эндпоинт отвечает 404."
        ),
    )
    prometheus_sd_cache_ttl_seconds: int = Field(
        default=120,
        ge=30,
        le=3600,
        description="TTL Redis-кэша целей HTTP SD (секунды).",
    )
    prometheus_sd_cache_schedule_enabled: bool = Field(
        default=True,
        description="Scheduler периодически обновляет кэш HTTP SD, чтобы API не ходил в БД.",
    )
    prometheus_sd_cache_refresh_interval_seconds: int = Field(
        default=60,
        ge=30,
        le=3600,
        description="Интервал refresh кэша HTTP SD в scheduler (секунды).",
    )
    prometheus_sd_cache_initial_delay_seconds: int = Field(
        default=5,
        ge=0,
        le=600,
        description="Задержка перед первым refresh кэша HTTP SD после старта scheduler.",
    )
    server_load_prometheus_sync_schedule_enabled: bool = Field(
        default=True,
        description=(
            "Включить фоновую синхронизацию servers.load_percent из Prometheus по расписанию (lifespan API). "
            "Запросы подписки /sub только читают уже сохранённые значения из БД."
        ),
    )
    server_load_prometheus_sync_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=86400,
        description=(
            "Интервал между синками load_percent из Prometheus (секунды). По умолчанию 300 (5 минут). "
            "Переменная: SERVER_LOAD_PROMETHEUS_SYNC_INTERVAL_SECONDS."
        ),
    )
    server_load_prometheus_sync_initial_delay_seconds: int = Field(
        default=30,
        ge=0,
        le=3600,
        description=(
            "Задержка перед первым тиком синхронизации нагрузки после старта процесса API (секунды). "
            "Переменная: SERVER_LOAD_PROMETHEUS_SYNC_INITIAL_DELAY_SECONDS."
        ),
    )

    server_reachability_schedule_enabled: bool = Field(
        default=True,
        description=(
            "Планировщик: периодический TCP-опрос активных provision_ready узлов (порт VPN, каскад, "
            "node_exporter) и запись снимков в Redis на SERVER_REACHABILITY_HISTORY_RETENTION_SECONDS."
        ),
    )
    server_reachability_interval_seconds: int = Field(
        default=60,
        ge=30,
        le=86400,
        description="Интервал между циклами опроса доступности узлов (секунды). Минимум 30.",
    )
    server_reachability_initial_delay_seconds: int = Field(
        default=40,
        ge=0,
        le=3600,
        description="Задержка перед первым циклом после старта процесса scheduler.",
    )
    server_reachability_tcp_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Таймаут TCP connect при фоновом опросе (секунды).",
    )
    server_reachability_history_retention_seconds: int = Field(
        default=86400,
        ge=3600,
        le=86400 * 14,
        description="Сколько секунд истории держать в Redis на узел (окно скользящее).",
    )
    server_reachability_parallelism: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Параллельных TCP-проб в одном цикле (каждый поток со своей sync-сессией БД).",
    )

    @field_validator("site_extra_addresses", mode="before")
    @classmethod
    def _parse_site_extra_addresses(cls, v: object) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            return [part.strip() for part in s.split(",") if part.strip()]
        return []

    def cors_allow_origins(self) -> list[str]:
        """cors_origins + https/http origin для SITE_ADDRESS и SITE_EXTRA_ADDRESSES."""
        from app.domain.subscription.public_base import site_address_to_public_origin

        seen: set[str] = set()
        out: list[str] = []
        for origin in self.cors_origins:
            if origin not in seen:
                seen.add(origin)
                out.append(origin)
        for raw in [self.site_address, *self.site_extra_addresses]:
            origin = site_address_to_public_origin(raw)
            if origin and origin not in seen:
                seen.add(origin)
                out.append(origin)
        return out

    @computed_field
    def sqlalchemy_database_url(self) -> str:
        raw = (self.database_url or "").strip()
        if raw:
            scheme, sep, rest = raw.partition("://")
            if not sep:
                return raw
            if scheme == "postgresql":
                return f"postgresql+psycopg://{rest}"
            return raw
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
