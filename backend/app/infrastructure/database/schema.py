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
import random
import time
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

log = logging.getLogger(__name__)

_INIT_NAME = "init.sql"
_MIGRATE_NAME = "migrate.sql"
_RPC_DIR_NAME = "rpc"
_ROLLUPS_DIR_NAME = "rollups"
_ROLLUP_PRE_PREFIX = "pre_"
_ROLLUP_POST_PREFIX = "post_"
# Один процесс на кластер: несколько uvicorn workers не должны параллельно гонять DDL.
_SCHEMA_MIGRATION_ADVISORY_LOCK_ID = 72490001
_PYTHON_ONE_TIME_MIGRATION_LOCK_ID = 72490002
_SCHEMA_MIGRATION_MAX_ATTEMPTS = 5
_DEADLOCK_SQLSTATE = "40P01"


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


import re

# PostgreSQL dollar-quoted строки: $$...$$ или $tag$...$tag$ (tag = [A-Za-z_][A-Za-z0-9_]*).
_DOLLAR_TAG_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def split_sql_statements(sql: str) -> list[str]:
    """Делит SQL на выражения по `;`, не разрывая тела `DO $$…$$` и `$tag$…$tag$`.

    Простое разбиение по «;» ломает PL/pgSQL и любые dollar-quoted строки
    (в том числе с именованным тегом, например `$mig$…$mig$`)."""
    cleaned = _strip_line_comments(sql)
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(cleaned)
    active_tag: str | None = None  # None → вне dollar-quote; иначе — открытый тег ("" для $$).
    while i < n:
        ch = cleaned[i]
        if ch == "$":
            m = _DOLLAR_TAG_RE.match(cleaned, i)
            if m is not None:
                tag = m.group(1) or ""
                if active_tag is None:
                    active_tag = tag
                    buf.append(m.group(0))
                    i = m.end()
                    continue
                if active_tag == tag:
                    active_tag = None
                    buf.append(m.group(0))
                    i = m.end()
                    continue
                # Другой тег внутри активного блока — просто текст.
                buf.append(m.group(0))
                i = m.end()
                continue
        if active_tag is None and ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
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


def _is_deadlock(exc: BaseException) -> bool:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) == _DEADLOCK_SQLSTATE


def _apply_schema_once(
    eng: Engine,
    *,
    init_path: Path,
    migrate_path: Path,
    rollup_pre_paths: list[Path],
    rpc_paths: list[Path],
    rollup_post_paths: list[Path],
) -> None:
    """init → migrate → rollups/pre → rpc → rollups/post в одной транзакции."""
    with eng.begin() as conn:
        # Сериализация миграций между uvicorn workers (иначе ALTER TABLE → deadlock).
        conn.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _SCHEMA_MIGRATION_ADVISORY_LOCK_ID},
        )
        _execute_sql_file(conn, init_path)
        _execute_sql_file(conn, migrate_path, allow_empty=True)
        for rollup_path in rollup_pre_paths:
            _execute_sql_file(conn, rollup_path)
        for rpc_path in rpc_paths:
            _execute_sql_file(conn, rpc_path)
        for rollup_path in rollup_post_paths:
            _execute_sql_file(conn, rollup_path)


def _python_one_time_migration_applied(conn, name: str) -> bool:
    try:
        row = conn.execute(
            text("SELECT 1 FROM schema_one_time_migrations WHERE name = :n"),
            {"n": name},
        ).first()
    except OperationalError:
        return False
    return row is not None


def _apply_python_one_time_migrations(eng: Engine) -> None:
    from app.domain.servers.traffic_archive import (
        ARCHIVE_REBUILD_ONE_TIME_MIGRATION,
        rebuild_inflated_traffic_archive_sync,
    )

    # Session-level lock на всё время: xact_lock отпускался до rebuild → два процесса
    # (api entrypoint + worker) могли параллельно гонять тяжёлый пересчёт архива.
    with eng.connect() as conn:
        conn.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": _PYTHON_ONE_TIME_MIGRATION_LOCK_ID},
        )
        try:
            if _python_one_time_migration_applied(conn, ARCHIVE_REBUILD_ONE_TIME_MIGRATION):
                return

            stats = rebuild_inflated_traffic_archive_sync()
            log.info(
                "one-time migration %s: users=%s rows_rebuilt=%s rows_forward_filled=%s",
                ARCHIVE_REBUILD_ONE_TIME_MIGRATION,
                stats.get("users"),
                stats.get("rows_rebuilt"),
                stats.get("rows_forward_filled"),
            )
            conn.execute(
                text(
                    "INSERT INTO schema_one_time_migrations (name) VALUES (:n) "
                    "ON CONFLICT (name) DO NOTHING",
                ),
                {"n": ARCHIVE_REBUILD_ONE_TIME_MIGRATION},
            )
            conn.commit()
        finally:
            conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _PYTHON_ONE_TIME_MIGRATION_LOCK_ID},
            )


def ensure_schema(engine: Engine | None = None) -> None:
    """init → migrate → rollups/pre → rpc → rollups/post; повтор при deadlock."""
    from app.infrastructure.database.session import engine as default_engine

    eng = engine or default_engine
    init_path, migrate_path = resolve_schema_sql_paths()
    rollup_pre_paths = resolve_rollup_sql_paths(phase="pre")
    rpc_paths = resolve_rpc_sql_paths()
    rollup_post_paths = resolve_rollup_sql_paths(phase="post")

    if not rollup_pre_paths:
        log.warning(
            "Каталог database/rollups/pre_*.sql не найден — rollup-таблицы должны быть "
            "созданы через migrate.sql; пересоберите образ API (COPY database/rollups).",
        )

    try:
        for attempt in range(1, _SCHEMA_MIGRATION_MAX_ATTEMPTS + 1):
            try:
                _apply_schema_once(
                    eng,
                    init_path=init_path,
                    migrate_path=migrate_path,
                    rollup_pre_paths=rollup_pre_paths,
                    rpc_paths=rpc_paths,
                    rollup_post_paths=rollup_post_paths,
                )
                _apply_python_one_time_migrations(eng)
                break
            except OperationalError as exc:
                if not _is_deadlock(exc) or attempt >= _SCHEMA_MIGRATION_MAX_ATTEMPTS:
                    log.exception("Ошибка применения схемы (%s, %s)", init_path, migrate_path)
                    raise
                delay = min(2.0**attempt + random.uniform(0, 0.5), 30.0)
                log.warning(
                    "Deadlock при миграции схемы, повтор %s/%s через %.1f с",
                    attempt + 1,
                    _SCHEMA_MIGRATION_MAX_ATTEMPTS,
                    delay,
                )
                if engine is None:
                    _dispose_connection_pools()
                time.sleep(delay)
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
