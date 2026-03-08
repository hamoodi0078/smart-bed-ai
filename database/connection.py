from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


class DatabaseConnection:
    SQLITE_FALLBACK_URL = "sqlite:///./data/manues.db"

    def __init__(self, database_url: str | None = None):
        if database_url is None:
            env_url = str(os.getenv("DATABASE_URL", "")).strip()
        else:
            env_url = str(database_url).strip()
        self.database_url = env_url or self.SQLITE_FALLBACK_URL
        self.engine: Engine = self._create_engine(self.database_url)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    @staticmethod
    def _create_engine(database_url: str) -> Engine:
        if str(database_url).lower().startswith("sqlite"):
            engine_kwargs: dict[str, object] = {
                "future": True,
                "connect_args": {"check_same_thread": False},
            }
            if (database_url == "sqlite://") or (":memory:" in database_url):
                engine_kwargs["poolclass"] = StaticPool
            return create_engine(database_url, **engine_kwargs)

        return create_engine(
            database_url,
            future=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
        )

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_tables(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def health_check(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
