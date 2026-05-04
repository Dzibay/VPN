from collections.abc import AsyncIterator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# psycopg3 по умолчанию готовит именованные server-side statements (_pg3_*).
# С пулом соединений и/или PgBouncer (transaction) это даёт DuplicatePreparedStatement
# на batch UPDATE/executemany (например при flush() после сбора трафика Xray).
_CONNECT_ARGS: dict = {"prepare_threshold": None}

# Синхронный движок и сессия — нужны worker'у (RQ запускает sync-задачи), scheduler'у и
# инициализации схемы (ensure_schema). API в эти объекты больше не ходит.
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args=_CONNECT_ARGS,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db_sync() -> Generator[Session, None, None]:
    """Синхронная сессия (sync-зависимости / совместимость со старым кодом)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_readonly_sync() -> Generator[Session, None, None]:
    """Read-only sync сессия: rollback на ошибке (PostgreSQL иначе помечает транзакцию failed)."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Асинхронный движок и сессия — для всех HTTP-эндпоинтов API. Один и тот же DSN
# (postgresql+psycopg://) одинаково работает в sync- и async-режимах SQLAlchemy 2.0
# поверх psycopg3. Отдельный драйвер (asyncpg) не нужен.
async_engine = create_async_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    connect_args=_CONNECT_ARGS,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Async-сессия для FastAPI: автокоммит на выходе, откат при исключении."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def get_db_readonly() -> AsyncIterator[AsyncSession]:
    """Read-only async-сессия: rollback на ошибке, без commit."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
