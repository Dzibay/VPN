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
