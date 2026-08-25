# Path: utils/postgres/base.py
# Description: Database client for PostgreSQL.

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL.get_secret_value(),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_timeout=30,
)

SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

DatabaseBase = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Get Database Session."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
