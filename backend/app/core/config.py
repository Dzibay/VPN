from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
            "Единый секрет HS256 для JWT (портал и админ-API). "
            "Пусто — выводится из ADMIN_EMAIL+ADMIN_PASSWORD или небезопасный ключ в DEBUG."
        ),
    )
    admin_email: str = Field(
        default="",
        description="Email администратора (вход через POST /api/auth/login вместе с ADMIN_PASSWORD).",
    )
    admin_password: str = Field(
        default="",
        description="Пароль администратора. Вместе с admin_email защищает админ-эндпоинты.",
    )
    telegram_bot_api_secret: str = Field(
        default="",
        description=(
            "Секрет для POST /api/auth/telegram и GET /api/telegram/subscription-open-clients: "
            "заголовок X-Telegram-Bot-Secret (вызывает только бэкенд бота, не Telegram-клиент). "
            "Пусто — эндпоинты отвечают 503."
        ),
    )
    subscription_public_base_url: str = Field(
        default="",
        description=(
            "Публичный HTTPS-Origin для ссылок на подписку и happ:// (напр. /sub/{token}/open/happ), "
            "напр. https://api.vpn.example.com (без слэша в конце). Рекомендуется всегда указывать "
            "с https:// для продакшена. Пусто — собирается из Host и X-Forwarded-Proto входящего запроса "
            "(чтобы не получать http:// за nginx в Docker см. переменную uvicorn FORWARDED_ALLOW_IPS)."
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
    subscription_open_spa_base_url: str = Field(
        default="",
        description=(
            "Origin сайта с Vue, если он не совпадает с API: редирект GET /sub/{token}/open/{client} "
            "ведёт на {этот_origin}/sub/{token}/open/{client} . Пусто — как subscription_public_base_url / Host."
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
        description="URL install-release.sh на удалённом хосте (curl/wget).",
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
            "Каскадный РФ-вход: geosite:ru+geoip:ru в direct, остальное на внешний exit. "
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
