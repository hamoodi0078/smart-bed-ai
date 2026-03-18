from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


class DatabaseConnection:
    SQLITE_FALLBACK_URL = "sqlite:///./data/manues.db"
    SCHEMA_META_TABLE = "schema_meta"
    SCHEMA_VERSION_KEY = "schema_version"
    CURRENT_SCHEMA_VERSION = 1

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
        self._ensure_schema_version()
        self._assert_required_tables_present()

    def _ensure_schema_version(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {self.SCHEMA_META_TABLE} "
                    "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
            )
            raw_value = connection.execute(
                text(
                    f"SELECT value FROM {self.SCHEMA_META_TABLE} "
                    "WHERE key = :key"
                ),
                {"key": self.SCHEMA_VERSION_KEY},
            ).scalar_one_or_none()
            try:
                current = int(str(raw_value or "0").strip())
            except Exception:
                current = 0

            if current < self.CURRENT_SCHEMA_VERSION:
                # Current migration strategy is table-first: ensure ORM metadata is present.
                Base.metadata.create_all(bind=self.engine)
                updated = connection.execute(
                    text(
                        f"UPDATE {self.SCHEMA_META_TABLE} SET value = :value "
                        "WHERE key = :key"
                    ),
                    {"key": self.SCHEMA_VERSION_KEY, "value": str(self.CURRENT_SCHEMA_VERSION)},
                )
                if int(getattr(updated, "rowcount", 0) or 0) == 0:
                    connection.execute(
                        text(
                            f"INSERT INTO {self.SCHEMA_META_TABLE} (key, value) "
                            "VALUES (:key, :value)"
                        ),
                        {"key": self.SCHEMA_VERSION_KEY, "value": str(self.CURRENT_SCHEMA_VERSION)},
                    )

    def _assert_required_tables_present(self) -> None:
        expected = set(Base.metadata.tables.keys())
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        missing = sorted(expected - existing)
        if not missing:
            return
        Base.metadata.create_all(bind=self.engine)
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        missing = sorted(expected - existing)
        if missing:
            raise RuntimeError(
                "Database schema is incomplete; missing required tables: "
                + ", ".join(missing)
            )

    def schema_version(self) -> int:
        with self.engine.connect() as connection:
            raw_value = connection.execute(
                text(
                    f"SELECT value FROM {self.SCHEMA_META_TABLE} "
                    "WHERE key = :key"
                ),
                {"key": self.SCHEMA_VERSION_KEY},
            ).scalar_one_or_none()
        try:
            return int(str(raw_value or "0").strip())
        except Exception:
            return 0

    def health_check(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
