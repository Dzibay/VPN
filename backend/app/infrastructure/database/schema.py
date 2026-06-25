"""
Идемпотентное приведение схемы PostgreSQL: database/init.sql (CREATE/индексы),
затем database/migrate.sql (опционально: может содержать только комментарии),
затем ``database/rollups/pre_*.sql`` (rollup-таблицы),
затем все ``database/rpc/*.sql``,
затем ``database/rollups/post_*.sql`` (materialized views).

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
_RPC_DIR_NAME = "rpc"
_ROLLUPS_DIR_NAME = "rollups"
_ROLLUP_PRE_PREFIX = "pre_"
_ROLLUP_POST_PREFIX = "post_"


def _repo_root_candidates() -> list[Path]:
    """Родительские каталоги от этого файла — ищем database/init.sql (устойчиво к глубине вложения)."""
    d = Path(__file__).resolve().parent
    roots: list[Path] = []
    for _ in range(24):
        roots.append(d)
        parent = d.parent
        if parent == d:
            break
        d = parent
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


def resolve_rollup_sql_paths(*, phase: str) -> list[Path]:
    """``pre_*`` — до RPC (rollup-таблицы); ``post_*`` — после RPC (materialized views)."""
    init_path, _migrate_path = resolve_schema_sql_paths()
    rollups_dir = init_path.parent / _ROLLUPS_DIR_NAME
    if not rollups_dir.is_dir():
        return []
    prefix = _ROLLUP_PRE_PREFIX if phase == "pre" else _ROLLUP_POST_PREFIX
    return sorted(
        p for p in rollups_dir.glob(f"{prefix}*.sql") if p.is_file()
    )


def resolve_rpc_sql_paths() -> list[Path]:
    """Файлы ``database/rpc/*.sql`` в алфавитном порядке (CREATE OR REPLACE FUNCTION и т.п.)."""
    init_path, _migrate_path = resolve_schema_sql_paths()
    rpc_dir = init_path.parent / _RPC_DIR_NAME
    if not rpc_dir.is_dir():
        return []
    return sorted(p for p in rpc_dir.glob("*.sql") if p.is_file())


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


def _execute_sql_file(conn, path: Path, *, allow_empty: bool = False) -> None:
    statements = split_sql_statements(path.read_text(encoding="utf-8"))
    if not statements:
        if allow_empty:
            log.debug("SQL-файл без исполняемых выражений (пропуск): %s", path)
            return
        raise ValueError(f"В {path} нет исполняемых выражений.")
    for stmt in statements:
        conn.execute(text(stmt))


def _dispose_connection_pools() -> None:
    """Сброс пулов после DDL — старые соединения не держат планы с устаревшими OID."""
    from app.infrastructure.database.session import async_engine, engine as sync_engine

    sync_engine.dispose()
    async_engine.sync_engine.dispose()


def ensure_schema(engine: Engine | None = None) -> None:
    """init → migrate → rollups/pre → rpc → rollups/post в одной транзакции."""
    from app.infrastructure.database.session import engine as default_engine

    eng = engine or default_engine
    init_path, migrate_path = resolve_schema_sql_paths()
    rollup_pre_paths = resolve_rollup_sql_paths(phase="pre")
    rpc_paths = resolve_rpc_sql_paths()
    rollup_post_paths = resolve_rollup_sql_paths(phase="post")

    try:
        with eng.begin() as conn:
            _execute_sql_file(conn, init_path)
            _execute_sql_file(conn, migrate_path, allow_empty=True)
            for rollup_path in rollup_pre_paths:
                _execute_sql_file(conn, rollup_path)
            for rpc_path in rpc_paths:
                _execute_sql_file(conn, rpc_path)
            for rollup_path in rollup_post_paths:
                _execute_sql_file(conn, rollup_path)
    except SQLAlchemyError:
        log.exception("Ошибка применения схемы (%s, %s)", init_path, migrate_path)
        raise
    finally:
        if engine is None:
            _dispose_connection_pools()

    rollup_names = ", ".join(
        p.name for p in (*rollup_pre_paths, *rollup_post_paths)
    ) or "—"
    rpc_names = ", ".join(p.name for p in rpc_paths) or "—"
    log.info(
        "Схема БД синхронизирована (%s + %s; rollups: %s; rpc: %s)",
        init_path.name,
        migrate_path.name,
        rollup_names,
        rpc_names,
    )
