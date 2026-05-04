from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Iterator

from loguru import logger
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Base

_DEFAULT_RETRY_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0


class DatabaseConnection:
    SQLITE_FALLBACK_URL = "sqlite:///./data/manues.db"
    SCHEMA_META_TABLE = "schema_meta"
    SCHEMA_VERSION_KEY = "schema_version"
    CURRENT_SCHEMA_VERSION = 1

    def __init__(
        self,
        database_url: str | None = None,
        retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS,
        retry_delay: float = _DEFAULT_RETRY_DELAY_SECONDS,
    ):
        if database_url is None:
            env_url = str(os.getenv("DATABASE_URL", "")).strip()
            if not env_url:
                import sys
                is_production = str(os.getenv("ENVIRONMENT", "")).strip().lower() in ("production", "prod")
                if is_production:
                    raise RuntimeError(
                        "DATABASE_URL is required in production. "
                        "Set it via the DATABASE_URL environment variable."
                    )
        else:
            env_url = str(database_url).strip()
        self.database_url = env_url or self.SQLITE_FALLBACK_URL
        self._retry_attempts = max(1, retry_attempts)
        self._retry_delay = max(0.1, retry_delay)
        self.engine: Engine = self._create_engine_with_retry()
        self._session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    def _create_engine_with_retry(self) -> Engine:
        engine = self._create_engine(self.database_url)
        attempts = self._retry_attempts
        delay = self._retry_delay
        safe_url = self._safe_url()

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=delay, min=delay, max=delay * 5),
            retry=retry_if_exception_type(Exception),
            before_sleep=lambda rs: logger.warning(
                "DB connection attempt {}/{} failed: {} — retrying",
                rs.attempt_number, attempts, rs.outcome.exception(),
            ),
            reraise=False,
        )
        def _probe():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

        try:
            _probe()
            logger.info("Database connected: {}", safe_url)
        except Exception:
            logger.error("All {} DB connection attempts failed: {}", attempts, safe_url)
        return engine

    def _safe_url(self) -> str:
        url = self.database_url
        if "@" in url:
            scheme_end = url.find("://")
            at_pos = url.rfind("@")
            if scheme_end != -1 and at_pos > scheme_end:
                return url[: scheme_end + 3] + "***@" + url[at_pos + 1 :]
        return url

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
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
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
        """Check database connectivity and health.
        
        Returns:
            True if database is healthy, False otherwise
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error("Database health check failed: {}", exc)
            return False
    
    def get_pool_status(self) -> dict[str, int]:
        """Get current connection pool statistics.
        
        Returns:
            Dict with pool size, checked out connections, and overflow
        """
        pool = self.engine.pool
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_in": pool.checkedin(),
        }
