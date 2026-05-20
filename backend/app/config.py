from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    telegram_bot_api_secret: str = Field(
        default="",
        description=(
            "Секрет для POST /api/auth/telegram, POST /api/telegram/link, POST /api/telegram/site-link/start, "
            "GET /api/telegram/referral/me, DELETE /api/telegram/subscription-devices/{device_id}, "
            "GET /api/telegram/payments/tribute-links, POST /api/payments/tribute/webhook-test, "
            "GET /api/telegram/notification-tasks, POST /api/telegram/notification-tasks/completed, "
            "GET /api/telegram/users, GET /api/telegram/users/{topic_id} и "
            "GET /api/telegram/subscription-open-clients: "
            "заголовок X-Telegram-Bot-Secret (вызывает только бэкенд бота, не Telegram-клиент). "
            "Пусто — эндпоинты отвечают 503."
        ),
    )
    site_address: str = Field(
        default="",
        description=(
            "Публичный URL сайта (env SITE_ADDRESS): полный URL или host[:port] без схемы. "
            "Единственный источник origin для SPA, рефералов, ссылок бота и редиректов /sub/…"
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

    tribute_api_key: str = Field(
        default="",
        description=(
            "Api-Key Tribute (Creator Dashboard → Settings → API Keys). Используется ТОЛЬКО как "
            "секрет для проверки подписи webhook (заголовок trbt-signature, HMAC-SHA256 от raw body). "
            "Пусто — POST /api/payments/tribute/webhook отвечает 503 (эндпоинт отключён)."
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
    provision_ssh_user: str = Field(
        default="root",
        description="Пользователь SSH для установки xray на узел (пробуется первым).",
    )
    provision_ssh_user_fallback: str = Field(
        default="user",
        description=(
            "Второй логин SSH, если к первому отказ (Permission denied, publickey). "
            "Пусто — не пробовать другого пользователя."
        ),
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
    xray_traffic_batch_job_timeout_seconds: int = Field(
        default=7200,
        ge=300,
        le=86400,
        description="Таймаут RQ для батч-задачи сбора трафика по всем серверам.",
    )
    trial_traffic_limit_enabled: bool = Field(
        default=True,
        description=(
            "После батч-сбора трафика Xray: сравнивать накопленный трафик с users.traffic_limit_bytes "
            "и при превышении ставить sync клиентов на узлах (снятие UUID с конфигов)."
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
            "Планировщик API: раз в сутки (локальное время процесса) ставить в очередь RQ "
            "синхронизацию клиентов Xray на всех узлах: перебор узлов через тот же путь, что и при регистрации "
            "(динамический diff без рестарта при возможности и полная перезапись config для согласованности)."
        ),
    )
    subscription_daily_xray_clients_sync_hour_local: int = Field(
        default=0,
        ge=0,
        le=23,
        description="Час локального времени процесса API для ежедневного sync Xray.",
    )
    subscription_daily_xray_clients_sync_minute_local: int = Field(
        default=5,
        ge=0,
        le=59,
        description="Минута локального времени процесса API.",
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
            "Раз в сутки (локальное время процесса) создавать задачи ``notify_sub_expire_3d`` / "
            "``notify_sub_expire_1d`` / ``notify_sub_expire_0d`` для пользователей с активной конечной подпиской и telegram_id."
        ),
    )
    subscription_expiry_notify_hour_local: int = Field(
        default=12,
        ge=0,
        le=23,
        description="Локальный час ежедневной проверки срока подписки (например 12 — полдень).",
    )
    subscription_expiry_notify_minute_local: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Локальная минута проверки срока подписки.",
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
