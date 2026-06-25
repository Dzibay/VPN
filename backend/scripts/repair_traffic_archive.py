"""
Пересчёт раздутого архива трафика (servers.id=0) из raw_up/raw_down.

Запуск на сервере (из каталога deploy, внутри контейнера api):
  docker compose exec api python scripts/repair_traffic_archive.py

Повторный принудительный пересчёт (игнорировать schema_one_time_migrations):
  docker compose exec api python scripts/repair_traffic_archive.py --force

Локально из backend/:
  python scripts/repair_traffic_archive.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_import_path() -> None:
    root = str(_backend_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_env() -> None:
    from dotenv import load_dotenv

    env_path = _backend_root() / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересчёт архива трафика server_id=0")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Выполнить даже если одноразовая миграция уже отмечена в БД",
    )
    args = parser.parse_args()

    _ensure_import_path()
    _load_env()

    from sqlalchemy import text

    from app.domain.servers.traffic_archive import (
        ARCHIVE_REBUILD_ONE_TIME_MIGRATION,
        rebuild_inflated_traffic_archive_sync,
    )
    from app.infrastructure.database.session import SessionLocal, engine

    if args.force:
        with SessionLocal() as session:
            session.execute(
                text(
                    "DELETE FROM schema_one_time_migrations WHERE name = :n",
                ),
                {"n": ARCHIVE_REBUILD_ONE_TIME_MIGRATION},
            )
            session.commit()
        print(f"Сброшена отметка миграции {ARCHIVE_REBUILD_ONE_TIME_MIGRATION}")

    stats = rebuild_inflated_traffic_archive_sync()
    print(
        "Готово: users={users}, rows_rebuilt={rows_rebuilt}, "
        "rows_forward_filled={rows_forward_filled}".format(**stats),
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_one_time_migrations (name) VALUES (:n) "
                "ON CONFLICT (name) DO NOTHING",
            ),
            {"n": ARCHIVE_REBUILD_ONE_TIME_MIGRATION},
        )
    print(f"Отметка {ARCHIVE_REBUILD_ONE_TIME_MIGRATION} записана.")


if __name__ == "__main__":
    main()
