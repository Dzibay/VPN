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

    admin_panel_password: str = Field(
        default="",
        description="Пароль входа в админку (фронт /api/users, /api/status). Пусто — без защиты.",
    )
    admin_jwt_secret: str = Field(
        default="",
        description="Секрет HS256 для JWT админки. Пусто — выводится из ADMIN_PANEL_PASSWORD.",
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
        description="Пользователь SSH для установки xray на узел.",
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
