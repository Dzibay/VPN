"""
Идемпотентное приведение схемы PostgreSQL: database/init.sql, затем database/migrate.sql.

docker-entrypoint-initdb.d выполняется только при пустом data directory; старые БД
догоняются при старте приложения через ensure_schema().
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

_INIT_NAME = "init.sql"
_MIGRATE_NAME = "migrate.sql"


def _repo_root_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    roots: list[Path] = []
    for levels in (4, 3):
        root = here
        for _ in range(levels):
            root = root.parent
        if root not in roots:
            roots.append(root)
    return roots


def resolve_schema_sql_paths() -> tuple[Path, Path]:
    """(init.sql, migrate.sql) рядом с корнем репозитория или в /app/database/."""
    for root in _repo_root_candidates():
        init_p = root / "database" / _INIT_NAME
        mig_p = root / "database" / _MIGRATE_NAME
        if init_p.is_file() and mig_p.is_file():
            return init_p, mig_p
    raise FileNotFoundError(
        f"Нужны database/{_INIT_NAME} и database/{_MIGRATE_NAME} "
        "(рядом с корнем репозитория или в /app/database/).",
    )


def _strip_line_comments(sql: str) -> str:
    out: list[str] = []
    for line in sql.splitlines():
        if line.lstrip().startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)


def split_sql_statements(sql: str) -> list[str]:
    """Делит SQL на выражения по `;`, не разрывая тела `DO $$ ... $$`.

    Простое разбиение по «;» ломает PL/pgSQL в migrate.sql."""
    cleaned = _strip_line_comments(sql)
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(cleaned)
    dollar_depth = 0  # счётчик незакрытых пар $$
    while i < n:
        if dollar_depth == 0 and cleaned[i : i + 2] == "$$":
            dollar_depth += 1
            buf.extend(["$", "$"])
            i += 2
            continue
        if dollar_depth > 0 and cleaned[i : i + 2] == "$$":
            dollar_depth -= 1
            buf.extend(["$", "$"])
            i += 2
            continue
        if dollar_depth == 0 and cleaned[i] == ";":
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(cleaned[i])
        i += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _execute_sql_file(conn, path: Path) -> None:
    statements = split_sql_statements(path.read_text(encoding="utf-8"))
    if not statements:
        raise ValueError(f"В {path} нет исполняемых выражений.")
    for stmt in statements:
        conn.execute(text(stmt))


def ensure_schema(engine: Engine | None = None) -> None:
    """init.sql → migrate.sql в одной транзакции."""
    from app.database.session import engine as default_engine

    eng = engine or default_engine
    init_path, migrate_path = resolve_schema_sql_paths()

    try:
        with eng.begin() as conn:
            _execute_sql_file(conn, init_path)
            _execute_sql_file(conn, migrate_path)
    except SQLAlchemyError:
        log.exception("Ошибка применения схемы (%s, %s)", init_path, migrate_path)
        raise

    log.info("Схема БД синхронизирована (%s + %s)", init_path.name, migrate_path.name)
