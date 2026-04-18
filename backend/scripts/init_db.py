"""
Применяет database/init.sql к БД через SQLAlchemy engine (app.database.session).

Переменные подключения — из backend/.env: DATABASE_URL или DB_HOST / DB_USER / DB_PASSWORD / DB_NAME (см. app.core.config).

Запуск из корня репозитория: python backend/scripts/init_db.py
или из backend: python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


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


def _strip_line_comments(sql: str) -> str:
    """Убирает строки с -- чтобы «;» внутри комментариев не ломали разбор."""
    out: list[str] = []
    for line in sql.splitlines():
        if line.lstrip().startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)


def _split_statements(sql: str) -> list[str]:
    cleaned = _strip_line_comments(sql)
    parts: list[str] = []
    for raw in cleaned.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        parts.append(stmt)
    return parts


def main() -> None:
    _ensure_import_path()
    _load_env()

    try:
        from app.database.session import engine
    except Exception as e:
        print(
            "Не удалось инициализировать подключение (проверьте DATABASE_URL или DB_* в backend/.env):",
            e,
            file=sys.stderr,
        )
        sys.exit(1)

    sql_path = _repo_root() / "database" / "init.sql"
    if not sql_path.is_file():
        print(f"Не найден файл: {sql_path}", file=sys.stderr)
        sys.exit(1)

    sql_text = sql_path.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)
    if not statements:
        print("В init.sql нет исполняемых выражений.", file=sys.stderr)
        sys.exit(1)

    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except SQLAlchemyError as e:
        print(f"Ошибка при выполнении SQL: {e}", file=sys.stderr)
        sys.exit(1)

    print("Схема применена:", sql_path)


if __name__ == "__main__":
    main()
