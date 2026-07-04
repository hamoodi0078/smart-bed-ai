from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

from loguru import logger
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Base

try:
    import asyncpg as _asyncpg
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker as _async_sessionmaker,
        create_async_engine,
    )
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _asyncpg = None  # type: ignore[assignment]
    _ASYNCPG_AVAILABLE = False

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
                # The deployment stack sets DANAH_ENV (Dockerfile, compose);
                # ENVIRONMENT is kept for backwards compatibility. Without this
                # guard a missing DATABASE_URL silently falls back to SQLite.
                env_name = str(
                    os.getenv("DANAH_ENV") or os.getenv("ENVIRONMENT") or ""
                ).strip().lower()
                if env_name in ("production", "prod"):
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

        try:
            from config.settings import settings as _s
            _pool_size = _s.db_pool_size
            _max_overflow = _s.db_max_overflow
            _pool_timeout = _s.db_pool_timeout
            _pool_recycle = _s.db_pool_recycle
        except Exception:
            _pool_size, _max_overflow, _pool_timeout, _pool_recycle = 10, 20, 30.0, 3600

        return create_engine(
            database_url,
            future=True,
            pool_size=_pool_size,
            max_overflow=_max_overflow,
            pool_timeout=_pool_timeout,
            pool_pre_ping=True,
            pool_recycle=_pool_recycle,
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


class AsyncDatabaseConnection:
    """High-performance async PostgreSQL layer backed by asyncpg + SQLAlchemy asyncio.

    Provides two access modes that share the same underlying asyncpg driver:

    * ``acquire()`` — raw asyncpg ``Connection`` for single-statement, bulk-insert,
      or copy-based queries where the ORM is unnecessary overhead.
    * ``get_session()`` — SQLAlchemy ``AsyncSession`` for ORM-level async operations
      that mirror the sync ``DatabaseConnection.get_session()`` interface.

    Lifecycle::

        db = AsyncDatabaseConnection()
        await db.initialize()        # call once at app startup
        ...                          # use acquire() / get_session()
        await db.close()             # call on app shutdown

    Parameters
    ----------
    database_url:
        PostgreSQL URL (``postgresql://…`` or ``postgresql+psycopg2://…``).
        Falls back to the ``DATABASE_URL`` environment variable.
    min_pool_size / max_pool_size:
        asyncpg pool bounds forwarded to ``asyncpg.create_pool()``.
    command_timeout:
        Per-statement timeout in seconds forwarded to asyncpg.
    """

    _DEFAULT_MIN = 2
    _DEFAULT_MAX = 10

    def __init__(
        self,
        database_url: str | None = None,
        min_pool_size: int | None = None,
        max_pool_size: int | None = None,
        command_timeout: float | None = None,
    ) -> None:
        if not _ASYNCPG_AVAILABLE:
            raise RuntimeError(
                "asyncpg is not installed. Run: pip install asyncpg"
            )
        raw_url = str(database_url or os.getenv("DATABASE_URL", "")).strip()
        if not raw_url or raw_url.lower().startswith("sqlite"):
            raise ValueError(
                "AsyncDatabaseConnection requires a PostgreSQL URL. "
                "asyncpg does not support SQLite."
            )
        self._dsn = self._to_asyncpg_dsn(raw_url)
        self._engine_url = self._to_async_engine_url(raw_url)

        try:
            from config.settings import settings as _s
            _cfg_min = _s.db_async_pool_min
            _cfg_max = _s.db_async_pool_max
            _cfg_timeout = _s.db_async_command_timeout
        except Exception:
            _cfg_min, _cfg_max, _cfg_timeout = self._DEFAULT_MIN, self._DEFAULT_MAX, 30.0

        self._min_size = max(1, int(min_pool_size if min_pool_size is not None else _cfg_min))
        self._max_size = max(self._min_size, int(max_pool_size if max_pool_size is not None else _cfg_max))
        self._command_timeout = max(1.0, float(command_timeout if command_timeout is not None else _cfg_timeout))

        self._pool: Any = None       # asyncpg.Pool
        self._engine: Any = None     # AsyncEngine
        self._session_factory: Any = None
        self._initialized = False

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_asyncpg_dsn(url: str) -> str:
        """Strip SQLAlchemy dialect prefix so asyncpg.create_pool() accepts it."""
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
            if url.startswith(prefix):
                return url.replace(prefix, "postgresql://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        return url

    @staticmethod
    def _to_async_engine_url(url: str) -> str:
        """Ensure the URL uses the postgresql+asyncpg:// dialect for SQLAlchemy."""
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url  # already postgresql+asyncpg://

    def _safe_url(self) -> str:
        url = self._dsn
        if "@" in url:
            sep = url.find("://")
            at = url.rfind("@")
            if sep != -1 and at > sep:
                return url[: sep + 3] + "***@" + url[at + 1 :]
        return url

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the asyncpg pool and SQLAlchemy async engine.

        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._initialized:
            return
        self._pool = await _asyncpg.create_pool(  # type: ignore[union-attr]
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            command_timeout=self._command_timeout,
        )
        self._engine = create_async_engine(
            self._engine_url,
            future=True,
            pool_size=self._max_size,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        self._session_factory = _async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        self._initialized = True
        logger.info("AsyncDatabaseConnection ready: {}", self._safe_url())

    async def close(self) -> None:
        """Drain connections and dispose the engine. Call on application shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._initialized = False
        logger.info("AsyncDatabaseConnection closed")

    # ------------------------------------------------------------------
    # Access modes
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Yield a raw asyncpg ``Connection`` from the pool.

        Use for bulk inserts, COPY operations, or queries where the ORM
        adds unnecessary overhead.

        Example::

            async with db.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", uid)
        """
        if self._pool is None:
            raise RuntimeError("Call await db.initialize() before using the pool.")
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Yield a SQLAlchemy ``AsyncSession`` with automatic commit/rollback.

        Example::

            async with db.get_session() as session:
                result = await session.execute(select(User).where(...))
        """
        if self._session_factory is None:
            raise RuntimeError("Call await db.initialize() before using sessions.")
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Ping the database; returns True on success, False on any error."""
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as exc:
            logger.error("Async DB health check failed: {}", exc)
            return False

    async def pool_status(self) -> dict[str, int]:
        """Return current asyncpg pool statistics."""
        if self._pool is None:
            return {"min_size": 0, "max_size": 0, "size": 0, "free_size": 0}
        return {
            "min_size": self._pool.get_min_size(),
            "max_size": self._pool.get_max_size(),
            "size": self._pool.get_size(),
            "free_size": self._pool.get_free_size(),
        }

    async def create_tables(self) -> None:
        """Create all ORM-declared tables via the async engine (useful in tests)."""
        if self._engine is None:
            raise RuntimeError("Call await db.initialize() first.")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
