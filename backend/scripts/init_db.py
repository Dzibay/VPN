"""
Применяет database/init.sql и database/migrate.sql к БД (app.infrastructure.database.session).

Переменные подключения — из backend/.env: DATABASE_URL или DB_HOST / DB_USER / DB_PASSWORD / DB_NAME (см. app.config).

Запуск из корня репозитория: python backend/scripts/init_db.py
или из backend: python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    return _backend_root().parent


def _ensure_import_path() -> None:
    root = str(_backend_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_env() -> None:
    env_path = _backend_root() / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


def main() -> None:
    _ensure_import_path()
    _load_env()

    try:
        from app.infrastructure.database.schema import ensure_schema
    except Exception as e:
        print(
            "Не удалось импортировать ensure_schema (проверьте DATABASE_URL или DB_* в backend/.env):",
            e,
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        ensure_schema()
    except Exception as e:
        print(f"Ошибка при выполнении SQL: {e}", file=sys.stderr)
        sys.exit(1)

    root = _repo_root()
    print("Схема применена:", root / "database" / "init.sql", "+", root / "database" / "migrate.sql")


if __name__ == "__main__":
    main()
