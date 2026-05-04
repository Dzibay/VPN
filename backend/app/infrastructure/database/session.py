from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# psycopg3 по умолчанию готовит именованные server-side statements (_pg3_*).
# С пулом соединений и/или PgBouncer (transaction) это даёт DuplicatePreparedStatement
# на batch UPDATE/executemany (например при flush() после сбора трафика Xray).
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_readonly() -> Generator[Session, None, None]:
    """Read-only сессия: rollback на ошибке (PostgreSQL иначе помечает транзакцию failed)."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
